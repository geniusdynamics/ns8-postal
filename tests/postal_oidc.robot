*** Settings ***
Library    SSHLibrary
Suite Teardown    Remove OIDC fixtures

*** Variables ***
${LDAP_IMAGE}       ghcr.io/nethserver/openldap:2.8.1
${KEYCLOAK_IMAGE}   ghcr.io/geniusdynamics/keycloak:keycloak-ns8-sso
${LEMON_IMAGE}      ghcr.io/geniusdynamics/lemonldapng:lemonldapng-ns8-sso
${DOMAIN}           postal-sso.example.org
${POSTAL}           postal.${DOMAIN}
${KEYCLOAK}         keycloak.${DOMAIN}
${LEMON}            lemon.${DOMAIN}
${LEMON_PORTAL}     auth.${LEMON}
${OIDC_PASSWORD}    Oidc-Login-CI-2026
${FIXTURES}         /root/postal-oidc-ci
${postal_id}        ${EMPTY}
${keycloak_id}      ${EMPTY}
${lemon_id}         ${EMPTY}
${directory_id}     ${EMPTY}

*** Keywords ***
Run command
    [Arguments]    ${command}
    ${out}    ${error}    ${rc} =    Execute Command    ${command}    return_rc=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${out} ${error}
    RETURN    ${out}

Install OIDC fixture
    [Arguments]    ${image}
    ${out} =    Run command    add-module ${image} 1
    ${id} =    Evaluate    ast.literal_eval($out)['module_id']    modules=ast
    RETURN    ${id}

Remove OIDC fixtures
    FOR    ${id}    IN    ${postal_id}    ${lemon_id}    ${keycloak_id}    ${directory_id}
        IF    $id
            Run command    remove-module --no-preserve ${id}
        END
    END

Trust the CI certificate from Postal
    Run command    runagent -m ${postal_id} podman exec -i --user 0 postal-app sh -c 'cat > /usr/local/share/ca-certificates/postal-oidc-ci.crt && update-ca-certificates >/dev/null' < ${FIXTURES}/ca.crt
    Run command    ip=$(hostname -I | cut -d " " -f1) && printf '%s %s %s\n' "$ip" "${KEYCLOAK}" "${LEMON_PORTAL}" | runagent -m ${postal_id} podman exec -i --user 0 postal-app sh -c 'cat >> /etc/hosts'

Configure managed Postal provider
    [Arguments]    ${id}
    ${uuid} =    Run command    redis-cli --no-auth-warning hget cluster/module_uuid ${id}
    Run command    api-cli run module/${postal_id}/configure-module --data '{"host":"${POSTAL}","oidc_enabled":true,"oidc_provider":"${uuid}","oidc_domain":"${DOMAIN}"}'
    ${config} =    Run command    api-cli run module/${postal_id}/get-configuration
    ${data} =    Evaluate    json.loads($config)    modules=json
    Should Be Equal    ${data}[oidc_provider]    ${uuid}
    Should Be Equal    ${data}[oidc_identifier]    ${postal_id}
    Should Be True    ${data}[oidc_secret_set]
    Should Not Contain    ${data}    oidc_secret
    Trust the CI certificate from Postal

Provision matching users
    [Arguments]    ${user}
    Run command    api-cli run module/${directory_id}/add-user --data '{"user":"${user}","display_name":"Postal User","mail":"${user}@${DOMAIN}","password":"${OIDC_PASSWORD}"}'
    Run command    runagent -m ${postal_id} podman exec postal-app bundle exec rails runner 'User.create!(first_name: "Postal", last_name: "User", email_address: "${user}@${DOMAIN}", password: "${OIDC_PASSWORD}", admin: true)'

Login through Postal
    [Arguments]    ${host}    ${kind}    ${user}    ${issuer_path}
    Run command    python3 ${FIXTURES}/oidc_login.py ${POSTAL} ${host} ${kind} ${user} ${OIDC_PASSWORD}
    Run command    runagent -m ${postal_id} podman exec postal-app bundle exec rails runner 'u = User.find_by!(email_address: "${user}@${DOMAIN}"); abort "OIDC login not linked" unless u.oidc_uid.present? && u.oidc_issuer == "https://${host}${issuer_path}"'

*** Test Cases ***
Install the two NS8 providers and Postal
    Run command    install -d -m 0700 ${FIXTURES}
    Put File    ${CURDIR}/oidc_login.py    ${FIXTURES}/oidc_login.py
    ${directory} =    Install OIDC fixture    ${LDAP_IMAGE}
    Set Suite Variable    ${directory_id}    ${directory}
    Run command    api-cli run module/${directory_id}/configure-module --data '{"provision":"new-domain","domain":"${DOMAIN}","admuser":"admin","admpass":"${OIDC_PASSWORD}"}'
    ${kc} =    Install OIDC fixture    ${KEYCLOAK_IMAGE}
    Set Suite Variable    ${keycloak_id}    ${kc}
    ${llng} =    Install OIDC fixture    ${LEMON_IMAGE}
    Set Suite Variable    ${lemon_id}    ${llng}
    ${pst} =    Install OIDC fixture    ${IMAGE_URL}
    Set Suite Variable    ${postal_id}    ${pst}
    Run command    api-cli run module/${keycloak_id}/configure-module --data '{"host":"${KEYCLOAK}","http2https":true,"lets_encrypt":false}'
    Wait Until Keyword Succeeds    150s    5s    Run command    curl -kfSs --resolve ${KEYCLOAK}:443:127.0.0.1 https://${KEYCLOAK}/realms/master/.well-known/openid-configuration >/dev/null
    Run command    api-cli run module/${keycloak_id}/configure-ns8-sso --data '{"enabled":true}'
    Run command    api-cli run module/${lemon_id}/configure-module --data '{"host":"${LEMON}","ldap_domain":"${DOMAIN}","http2https":true,"lets_encrypt":false}'
    Run command    api-cli run module/${lemon_id}/configure-ns8-sso --data '{"enabled":true}'
    Run command    api-cli run module/${postal_id}/configure-module --data '{"host":"${POSTAL}","smtp_port":2529,"http2https":true,"lets_encrypt":false}'
    Run command    cd ${FIXTURES} && openssl req -x509 -newkey rsa:2048 -nodes -subj /CN=Postal-OIDC-CI -keyout ca.key -out ca.crt -days 2 >/dev/null 2>&1
    Run command    cd ${FIXTURES} && openssl req -new -newkey rsa:2048 -nodes -subj /CN=${KEYCLOAK} -keyout tls.key -out tls.csr >/dev/null 2>&1 && printf '%s\n' 'subjectAltName=DNS:${KEYCLOAK},DNS:${LEMON_PORTAL},DNS:${POSTAL}' > tls.ext && openssl x509 -req -in tls.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out tls.crt -days 2 -extfile tls.ext
    Run command    cd ${FIXTURES} && jq -n --rawfile cert tls.crt --rawfile key tls.key '{certFile:($cert|@base64),keyFile:($key|@base64)}' | api-cli run module/traefik1/upload-certificate --data -
    Wait Until Keyword Succeeds    45s    3s    Run command    curl -fSs --cacert ${FIXTURES}/ca.crt --resolve ${KEYCLOAK}:443:127.0.0.1 https://${KEYCLOAK}/realms/master/.well-known/openid-configuration >/dev/null

Discover both providers
    ${out} =    Run command    api-cli run module/${postal_id}/list-oidc-providers
    ${catalog} =    Evaluate    json.loads($out)    modules=json
    Should Contain    ${catalog}[domains]    ${DOMAIN}
    ${managed} =    Evaluate    {p['module_id']:p for p in $catalog['providers'] if p['managed']}
    Should Contain    ${managed}    ${keycloak_id}
    Should Contain    ${managed}    ${lemon_id}
    Should Be Equal    ${managed}[${lemon_id}][domain]    ${DOMAIN}

Sign into Postal using NS8 Keycloak
    Provision matching users    postalkeycloak
    Configure managed Postal provider    ${keycloak_id}
    Login through Postal    ${KEYCLOAK}    keycloak    postalkeycloak    /realms/${DOMAIN}

Sign into Postal using NS8 LemonLDAP
    Provision matching users    postallemon
    Configure managed Postal provider    ${lemon_id}
    Login through Postal    ${LEMON_PORTAL}    lemonldapng    postallemon    /ns8-realms/${DOMAIN}

Sign into Postal using manually entered client credentials
    Provision matching users    postalmanual
    Run command    runagent -m ${keycloak_id} python3 -c 'import kcadmin, json, sys; domain, host = sys.argv[1:]; kcadmin.agent_client().post(f"/{domain}/clients", {"clientId":"postal-manual-ci","secret":"postal-manual-ci-secret","enabled":True,"protocol":"openid-connect","publicClient":False,"standardFlowEnabled":True,"redirectUris":[f"https://{host}/auth/oidc/callback"]})' ${DOMAIN} ${POSTAL}
    Run command    api-cli run module/${postal_id}/configure-module --data '{"host":"${POSTAL}","oidc_enabled":true,"oidc_provider":"","oidc_issuer":"https://${KEYCLOAK}/realms/${DOMAIN}","oidc_identifier":"postal-manual-ci","oidc_secret":"postal-manual-ci-secret","oidc_name":"Manual OIDC","oidc_discovery":true}'
    Trust the CI certificate from Postal
    Login through Postal    ${KEYCLOAK}    keycloak    postalmanual    /realms/${DOMAIN}
