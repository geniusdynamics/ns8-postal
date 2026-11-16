*** Settings ***
Library    SSHLibrary
Library    String

*** Variables ***
${HOST}           postal.example.org
${OIDC_SECRET}    T3st-OIDC-Secr3t-Value
${SMTP_PORT}      2525

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

Check the database dump of the backup
    ${out}    ${rc} =    Execute Command    runagent -m ${module_id} bash -c 'module-dump-state && grep -c "CREATE DATABASE" postal.sql && module-cleanup-state'
    ...    return_rc=True
    Should Be Equal As Integers    ${rc}    0

Check if postal is removed correctly
    ${rc} =    Execute Command    remove-module --no-preserve ${module_id}
    ...    return_rc=True  return_stdout=False
    Should Be Equal As Integers    ${rc}  0
