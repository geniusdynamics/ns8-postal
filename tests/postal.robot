*** Settings ***
Library    SSHLibrary
Library    String
Library    Collections

*** Variables ***
${HOST}           postal.example.org
${OIDC_SECRET}    T3st-OIDC-Secr3t-Value
${SMTP_PORT}      2525
${TRACK_PARENT}   example.net
${TRACK_HOST}     click.example.net

*** Keywords ***
Run configure-module
    [Arguments]    ${payload}
    ${out}    ${err}    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '${payload}'
    ...    return_rc=True    return_stderr=True
    RETURN    ${rc}    ${out}

Get configuration
    ${out}    ${rc} =    Execute Command    api-cli run module/${module_id}/get-configuration
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    RETURN    ${out}

Started at of containers
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} podman inspect -f '{{.Name}}={{.State.StartedAt}}' mariadb-app postal-app postal-smtp-app postal-worker-app
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    &{started} =    Create Dictionary
    FOR    ${line}    IN    @{out.splitlines()}
        ${name}    ${at} =    Evaluate    $line.split("=", 1)
        Set To Dictionary    ${started}    ${name}=${at}
    END
    RETURN    ${started}

Run Postal SQL
    [Arguments]    ${sql}
    ${b64} =    Evaluate    base64.b64encode($sql.encode()).decode()    modules=base64
    ${out}    ${err}    ${rc} =    Execute Command    echo ${b64} | base64 -d | runagent -m ${module_id} bash -c 'source database.env; podman exec -i -e MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-app mariadb -h 127.0.0.1 -u root postal'
    ...    return_rc=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${err}

Traefik routes
    ${out}    ${rc} =    Execute Command    api-cli run module/traefik1/list-routes
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    RETURN    ${out}

*** Test Cases ***
Check if postal is installed correctly
    ${output}  ${rc} =    Execute Command    add-module ${IMAGE_URL} 1
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}  0
    &{output} =    Evaluate    ${output}
    Set Suite Variable    ${module_id}    ${output.module_id}

Check if postal can be configured
    ${rc} =    Execute Command    api-cli run module/${module_id}/configure-module --data '{"host":"${HOST}","http2https":true,"lets_encrypt":false}'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0

Check if postal works as expected
    ${rc} =    Execute Command    bash -c 'for i in $(seq 1 60); do curl -k -s -o /dev/null -f --resolve ${HOST}:443:127.0.0.1 https://${HOST}/login && exit 0; sleep 5; done; exit 1'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0

Check that Postal runs in the production environment
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} podman exec postal-app cat /config/postal.yml
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Contain    ${out}    environment: "production"
    Should Not Contain    ${out}    secret_key

Check the SMTP banner on the module SMTP port
    ${out}    ${rc} =    Execute Command    python3 -c 'import smtplib; s = smtplib.SMTP("127.0.0.1", ${SMTP_PORT}, timeout=30); print(s.ehlo()[0], "starttls" if s.has_extn("starttls") else "no-starttls"); s.quit()'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Start With    ${out}    250
    Should Contain    ${out}    starttls

Check that the SMTP port is open in the firewall
    ${out}    ${rc} =    Execute Command    firewall-cmd --info-service=${module_id}
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Contain    ${out}    ${SMTP_PORT}/tcp

Configure delivery, IP pools, relays and OIDC
    ${payload} =    Catenate    SEPARATOR=
    ...    {"host":"${HOST}","http2https":true,"lets_encrypt":false,
    ...    "default_maximum_delivery_attempts":10,"default_maximum_hold_expiry_days":5,
    ...    "default_suppression_list_automatic_removal_days":20,
    ...    "default_spam_threshold":6,"default_spam_failure_threshold":25,
    ...    "use_ip_pools":true,
    ...    "smtp_relays":[{"host":"relay.example.net","port":587,"ssl_mode":"STARTTLS"}],
    ...    "oidc_enabled":true,"oidc_name":"Test SSO",
    ...    "oidc_issuer":"https://sso.example.org/realms/test",
    ...    "oidc_identifier":"postal","oidc_secret":"${OIDC_SECRET}",
    ...    "oidc_scopes":["openid","email","profile"],
    ...    "worker_threads":3,"max_message_size":20}
    ${rc}    ${out} =    Run configure-module    ${payload}
    Should Be Equal As Integers    ${rc}    0

Read the settings back without secrets
    ${out} =    Get configuration
    Should Not Contain    ${out}    ${OIDC_SECRET}
    &{conf} =    Evaluate    json.loads($out)    modules=json
    Should Be Equal As Integers    ${conf.default_maximum_delivery_attempts}    10
    Should Be Equal As Integers    ${conf.default_spam_threshold}    6
    Should Be Equal As Integers    ${conf.default_spam_failure_threshold}    25
    Should Be True    ${conf.use_ip_pools}
    Should Be True    ${conf.oidc_enabled}
    Should Be True    ${conf.oidc_secret_set}
    Should Be Equal    ${conf.oidc_issuer}    https://sso.example.org/realms/test
    Should Be Equal    ${conf.oidc_redirect_uri}    https://${HOST}/auth/oidc/callback
    Should Be Equal    ${conf.smtp_relays[0]['host']}    relay.example.net
    Should Not Contain    ${conf}    oidc_secret

Check the generated Postal configuration
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} podman exec postal-app cat /config/postal.yml
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Contain    ${out}    default_maximum_delivery_attempts: 10
    Should Contain    ${out}    default_maximum_hold_expiry_days: 5
    Should Contain    ${out}    default_suppression_list_automatic_removal_days: 20
    Should Contain    ${out}    default_spam_threshold: 6
    Should Contain    ${out}    default_spam_failure_threshold: 25
    Should Contain    ${out}    use_ip_pools: true
    Should Contain    ${out}    threads: 3
    Should Contain    ${out}    max_message_size: 20
    Should Contain    ${out}    smtp_relays: ["smtp://relay.example.net:587?ssl_mode=STARTLS"]
    Should Contain    ${out}    issuer: "https://sso.example.org/realms/test"
    Should Contain    ${out}    scopes: ["openid", "email", "profile"]
    Should Not Contain    ${out}    ${OIDC_SECRET}

Check that secrets stay out of the module environment and postal.yml
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} bash -c 'cat environment postal.yml; stat -c "%a %n" postal.env secrets/secrets.env secrets/signing.key database.env'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Not Contain    ${out}    ${OIDC_SECRET}
    Should Contain    ${out}    600 postal.env
    Should Contain    ${out}    600 secrets/secrets.env
    Should Contain    ${out}    600 secrets/signing.key
    Should Contain    ${out}    600 database.env

Check that the OIDC login button is shown
    ${rc} =    Execute Command    bash -c 'for i in $(seq 1 60); do curl -k -s --resolve ${HOST}:443:127.0.0.1 https://${HOST}/login | grep -q "Login with Test SSO" && exit 0; sleep 5; done; exit 1'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Check that the OIDC secret reaches Postal
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} podman exec postal-app printenv OIDC_SECRET
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Be Equal    ${out}    ${OIDC_SECRET}

Refuse to disable local logins without OIDC
    ${rc}    ${out} =    Run configure-module    {"host":"${HOST}","oidc_enabled":false,"oidc_local_authentication_enabled":false}
    Should Not Be Equal As Integers    ${rc}    0
    ${out} =    Get configuration
    &{conf} =    Evaluate    json.loads($out)    modules=json
    Should Be True    ${conf.oidc_enabled}
    Should Be True    ${conf.oidc_local_authentication_enabled}

Keep the settings when fields are left out
    ${rc}    ${out} =    Run configure-module    {"host":"${HOST}","http2https":true,"lets_encrypt":false}
    Should Be Equal As Integers    ${rc}    0
    ${out} =    Get configuration
    &{conf} =    Evaluate    json.loads($out)    modules=json
    Should Be Equal As Integers    ${conf.default_maximum_delivery_attempts}    10
    Should Be True    ${conf.oidc_secret_set}

Check the web UI and the SMTP server after the changes
    ${rc} =    Execute Command    bash -c 'for i in $(seq 1 60); do curl -k -s -o /dev/null -f --resolve ${HOST}:443:127.0.0.1 https://${HOST}/login && exit 0; sleep 5; done; exit 1'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${out}    ${rc} =    Execute Command    python3 -c 'import smtplib; s = smtplib.SMTP("127.0.0.1", ${SMTP_PORT}, timeout=30); print(s.ehlo()[0]); s.quit()'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Start With    ${out}    250

Restart only the containers affected by a change
    ${before} =    Started at of containers
    ${rc}    ${out} =    Run configure-module    {"host":"${HOST}","oidc_name":"Other SSO"}
    Should Be Equal As Integers    ${rc}    0
    ${after} =    Started at of containers
    Should Be Equal    ${before}[mariadb-app]    ${after}[mariadb-app]
    Should Be Equal    ${before}[postal-smtp-app]    ${after}[postal-smtp-app]
    Should Be Equal    ${before}[postal-worker-app]    ${after}[postal-worker-app]
    Should Not Be Equal    ${before}[postal-app]    ${after}[postal-app]
    ${rc} =    Execute Command    bash -c 'for i in $(seq 1 60); do curl -k -s --resolve ${HOST}:443:127.0.0.1 https://${HOST}/login | grep -q "Login with Other SSO" && exit 0; sleep 5; done; exit 1'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0

Refuse a privileged SMTP port
    ${rc}    ${out} =    Run configure-module    {"host":"${HOST}","smtp_port":22}
    Should Not Be Equal As Integers    ${rc}    0

Route a track domain through Traefik
    Run Postal SQL    INSERT INTO domains (uuid, server_id, name, owner_type, owner_id, verified_at, created_at, updated_at) VALUES (UUID(), 1, '${TRACK_PARENT}', 'Server', 1, NOW(), NOW(), NOW()); INSERT INTO track_domains (uuid, server_id, domain_id, name, ssl_enabled, created_at, updated_at) VALUES (UUID(), 1, LAST_INSERT_ID(), 'click', 1, NOW(), NOW())
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} postal-track-routes
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    ${routes} =    Traefik routes
    Should Contain    ${routes}    ${module_id}-track-${TRACK_HOST}
    ${rc} =    Execute Command    bash -c 'for i in $(seq 1 30); do curl -k -s --resolve ${TRACK_HOST}:443:127.0.0.1 https://${TRACK_HOST}/ | grep -q "Hello." && exit 0; sleep 3; done; exit 1'
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}    0
    ${out} =    Get configuration
    &{conf} =    Evaluate    json.loads($out)    modules=json
    Should Be Equal    ${conf.track_domains[0]['name']}    ${TRACK_HOST}
    Should Be Equal    ${conf.track_domains[0]['status']}    no_lets_encrypt

Remove the route of a deleted track domain
    Run Postal SQL    DELETE FROM track_domains WHERE name = 'click'; DELETE FROM domains WHERE name = '${TRACK_PARENT}'
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} postal-track-routes
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    ${routes} =    Traefik routes
    Should Not Contain    ${routes}    ${module_id}-track-${TRACK_HOST}

Run the worker with the network of the node
    ${rc}    ${out} =    Run configure-module    {"host":"${HOST}","worker_host_network":true}
    Should Be Equal As Integers    ${rc}    0
    ${mode} =    Execute Command    runagent -m ${module_id} podman inspect -f '{{.HostConfig.NetworkMode}}' postal-worker-app
    Should Be Equal    ${mode.strip()}    host

Bind the primary address of the node from the worker
    ${ip} =    Execute Command    ip -4 -o route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}'
    ${ip} =    Set Variable    ${ip.strip()}
    Should Not Be Empty    ${ip}
    ${ruby} =    Catenate
    ...    ip = Struct.new(:ipv4, :ipv6, :hostname).new("${ip}", nil, "${HOST}");
    ...    ep = SMTPClient::Endpoint.new(SMTPClient::Server.new("${ip}", port: ${SMTP_PORT}, ssl_mode: "None"), "${ip}");
    ...    ep.start_smtp_session(source_ip_address: ip, allow_ssl: false);
    ...    puts "source=" + ep.smtp_client.source_address.to_s;
    ...    ep.finish_smtp_session;
    ...    puts "db=" + Organization.count.to_s
    ${out}    ${err}    ${rc} =    Execute Command    runagent -m ${module_id} podman exec postal-worker-app bundle exec rails runner '${ruby}'
    ...    return_rc=True    return_stderr=True
    Should Be Equal As Integers    ${rc}    0    ${err}
    Should Contain    ${out}    source=${ip}
    Should Contain    ${out}    db=

Run rspamd in the pod with its web interface
    ${rc}    ${out} =    Run configure-module    {"host":"${HOST}","rspamd_container":true,"rspamd_webui":true}
    Should Be Equal As Integers    ${rc}    0
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} podman exec postal-app cat /config/postal.yml
    ...    return_rc=True
    Should Contain    ${out}    port: 11333
    ${out} =    Get configuration
    &{conf} =    Evaluate    json.loads($out)    modules=json
    Should Be True    ${conf.rspamd_container}
    Should Not Contain    ${out}    CONTROLLER_PASSWORD
    # The worker, on the network of the node, reaches the rspamd controller
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} bash -c 'podman exec postal-worker-app curl -s http://127.0.0.2:$TCP_PORT/ping'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    Should Contain    ${out}    pong

Ask the rspamd password through Traefik
    ${out}    ${rc} =    Execute Command    api-cli run module/${module_id}/reveal-rspamd-password
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    &{reveal} =    Evaluate    json.loads($out)    modules=json
    Should Not Be Empty    ${reveal.password}
    ${anonymous} =    Execute Command    curl -k -s -o /dev/null -w '\%{http_code}' --resolve ${HOST}:443:127.0.0.1 https://${HOST}/rspamd/stat
    Should Be Equal    ${anonymous}    403
    ${authorized} =    Execute Command    curl -k -s -o /dev/null -w '\%{http_code}' -H 'Password: ${reveal.password}' --resolve ${HOST}:443:127.0.0.1 https://${HOST}/rspamd/stat
    Should Be Equal    ${authorized}    200
    ${page} =    Execute Command    curl -k -s --resolve ${HOST}:443:127.0.0.1 https://${HOST}/rspamd/
    Should Contain    ${page}    Rspamd

Switch the worker back to the pod and rspamd off
    ${rc}    ${out} =    Run configure-module    {"host":"${HOST}","worker_host_network":false,"rspamd_container":false,"rspamd_webui":false}
    Should Be Equal As Integers    ${rc}    0
    ${mode} =    Execute Command    runagent -m ${module_id} podman inspect -f '{{.HostConfig.NetworkMode}}' postal-worker-app
    Should Not Be Equal    ${mode.strip()}    host
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} podman exec postal-worker-app curl -sf http://127.0.0.1:9090/health
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0
    ${rc} =    Execute Command    runagent -m ${module_id} podman container exists rspamd-app
    ...    return_stdout=False    return_rc=True
    Should Not Be Equal As Integers    ${rc}    0
    ${status} =    Execute Command    curl -k -s -o /dev/null -w '\%{http_code}' --resolve ${HOST}:443:127.0.0.1 https://${HOST}/rspamd/stat
    Should Not Be Equal    ${status}    200

Check the database dump of the backup
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} bash -c 'module-dump-state && grep -c "CREATE DATABASE" postal.sql && module-cleanup-state'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0

Check if postal is removed correctly
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0
