*** Settings ***
Library    SSHLibrary

*** Variables ***
${HOST}            postal-update.example.org
${OIDC_SECRET}     Upd4te-OIDC-Secr3t
# The update scenarios start from the releases installed instances run:
# the latest one, and 1.1.0, the last one before the settings.json layout
@{RELEASES}        2.2.0    1.1.0

*** Keywords ***
Run on module
    [Arguments]    ${command}
    ${out}    ${err}    ${rc} =    Execute Command    runagent -m ${module_id} ${command}
    ...    return_rc=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${err}
    RETURN    ${out}

Postal SQL value
    [Arguments]    ${query}
    ${b64} =    Evaluate    base64.b64encode($query.encode()).decode()    modules=base64
    ${out}    ${err}    ${rc} =    Execute Command    echo ${b64} | base64 -d | runagent -m ${module_id} postal-mariadb mariadb -h 127.0.0.1 -u root -N -B postal
    ...    return_rc=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${err}
    RETURN    ${out.strip()}

Signing key digest
    ${out} =    Run on module    bash -c 'sha256sum secrets/signing.key config/signing.key 2>/dev/null | head -1 | cut -d" " -f1'
    RETURN    ${out.strip()}

Web answers
    ${rc} =    Execute Command    bash -c 'for i in $(seq 1 60); do curl -k -s -o /dev/null -f --resolve ${HOST}:443:127.0.0.1 https://${HOST}/login && exit 0; sleep 5; done; exit 1'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Wait for the SMTP port to be released
    # The released modules check the SMTP port with agent.tcp_port_in_use(),
    # which takes the connections left in TIME_WAIT (up to 60 seconds) by the
    # SMTP tests of the instance removed before for a service on the port
    ${rc} =    Execute Command    for i in $(seq 1 60); do python3 -c 'import socket; socket.socket().bind(("", 2525))' 2>/dev/null && exit 0; sleep 2; done; exit 1
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Update scenario
    [Arguments]    ${release}
    Log    Update from ${release} to ${IMAGE_URL}    console=${True}
    Wait for the SMTP port to be released
    ${out}    ${rc} =    Execute Command    add-module ghcr.io/geniusdynamics/postal:${release} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    add-module ${release} failed: ${out}
    # add-module prints a Python dict
    &{output} =    Evaluate    ast.literal_eval($out)    modules=ast
    Set Test Variable    ${module_id}    ${output.module_id}
    IF    '${release}' == '1.1.0'
        ${payload} =    Set Variable    {"host":"${HOST}","http2https":true,"lets_encrypt":false,"from_name":"Upgrade Sender","from_address":"sender@example.org"}
    ELSE
        ${payload} =    Set Variable    {"host":"${HOST}","http2https":true,"lets_encrypt":false,"from_name":"Upgrade Sender","from_address":"sender@example.org","default_spam_threshold":7,"default_maximum_delivery_attempts":9,"oidc_enabled":true,"oidc_issuer":"https://sso.example.org/realms/up","oidc_identifier":"postal","oidc_secret":"${OIDC_SECRET}"}
    END
    # The first start of the released versions races with the creation of
    # the schema (fixed by this branch: .postal-db-ready): a second
    # configuration, on the created schema, succeeds
    ${out}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
    ...    return_rc=True
    IF    ${rc} != 0
        Log    configure-module of ${release} failed once (${rc}): retrying    console=${True}
        Sleep    20s
        ${out}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
        ...    return_rc=True
    END
    Should Be Equal As Integers    ${rc}    0    configure-module of ${release} failed: ${out}
    Web answers
    # Data: a user, an organization and a mail server (with its message database)
    ${ruby} =    Catenate
    ...    u = User.create!(first_name: "Up", last_name: "Grade", email_address: "upgrade@example.org", password: "Upgrade-Passw0rd-1", admin: true);
    ...    o = Organization.create!(name: "Upgrade Org", permalink: "upgrade-org", time_zone: "UTC", owner: u);
    ...    s = o.servers.create!(name: "Upgrade Server", permalink: "upgrade-server", mode: "Live");
    ...    puts "server=" + s.id.to_s
    ${out} =    Run on module    podman exec postal-app bundle exec rails runner '${ruby}'
    Should Contain    ${out}    server=
    ${key_before} =    Signing key digest
    Should Not Be Empty    ${key_before}

    ${out}    ${rc} =    Execute Command    api-cli run update-module --data '{"module_url":"${IMAGE_URL}","instances":["${module_id}"]}'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0    update-module from ${release} failed: ${out}
    ${image_url} =    Run on module    printenv IMAGE_URL
    Should Be Equal    ${image_url.strip()}    ${IMAGE_URL}

    Web answers
    ${orgs} =    Postal SQL value    SELECT COUNT(*) FROM organizations WHERE permalink = 'upgrade-org'
    Should Be Equal    ${orgs}    1
    ${users} =    Postal SQL value    SELECT COUNT(*) FROM users WHERE email_address = 'upgrade@example.org'
    Should Be Equal    ${users}    1
    ${dbs} =    Postal SQL value    SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name LIKE 'postal-server-%'
    Should Be Equal    ${dbs}    1
    ${key_after} =    Signing key digest
    Should Be Equal    ${key_before}    ${key_after}
    ${yml} =    Run on module    podman exec postal-app cat /config/postal.yml
    Should Contain    ${yml}    environment: "production"
    Should Contain    ${yml}    web_hostname: "${HOST}"
    ${conf_json}    ${rc} =    Execute Command    api-cli run module/${module_id}/get-configuration
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Not Contain    ${conf_json}    ${OIDC_SECRET}
    &{conf} =    Evaluate    json.loads($conf_json)    modules=json
    Should Be Equal    ${conf.host}    ${HOST}
    Should Be Equal    ${conf.from_name}    Upgrade Sender
    Should Be Equal    ${conf.from_address}    sender@example.org
    IF    '${release}' != '1.1.0'
        Should Be Equal As Integers    ${conf.default_spam_threshold}    7
        Should Be Equal As Integers    ${conf.default_maximum_delivery_attempts}    9
        Should Be True    ${conf.oidc_enabled}
        Should Be True    ${conf.oidc_secret_set}
    END
    # The SMTP server answers after the update
    ${out}    ${rc} =    Execute Command    python3 -c 'import smtplib; s = smtplib.SMTP("127.0.0.1", 2525, timeout=30); print(s.ehlo()[0]); s.quit()'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    # A login of the user created before the update
    ${rc} =    Execute Command    bash -c 'jar=$(mktemp); tok=$(curl -k -s -c $jar --resolve ${HOST}:443:127.0.0.1 https://${HOST}/login | sed -n "s/.*name=\\"authenticity_token\\" value=\\"\\([^\\"]*\\)\\".*/\\1/p" | head -1); curl -k -s -b $jar -c $jar -o /dev/null -w "\%{redirect_url}" --resolve ${HOST}:443:127.0.0.1 --data-urlencode "authenticity_token=$tok" --data-urlencode "email_address=upgrade@example.org" --data-urlencode "password=Upgrade-Passw0rd-1" https://${HOST}/login | grep -qv "/login"'
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True    return_stdout=False
    Should Be Equal As Integers    ${rc}    0

*** Test Cases ***
Update from the latest release
    Update scenario    ${RELEASES}[0]

Update from the release before the settings.json layout
    Update scenario    ${RELEASES}[1]
