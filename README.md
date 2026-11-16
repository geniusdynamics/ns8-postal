# Postal for NethServer 8

<div align="center">
  <img src="ui/src/assets/module_default_logo.png" alt="Postal Logo" width="120" height="120">
  
  [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
  [![GitHub Actions](https://github.com/geniusdynamics/ns8-postal/workflows/Test%20module/badge.svg)](https://github.com/geniusdynamics/ns8-postal/actions)
  [![NethServer 8](https://img.shields.io/badge/NethServer-8-orange)](https://github.com/NethServer/ns8-core)
</div>

## 📧 Overview

**Postal** is a complete and fully featured mail server for use by websites & web servers. Think Sendgrid, Mailgun or Postmark but open source and ready for you to run on your own servers.

This module provides seamless integration of Postal with [NethServer 8](https://github.com/NethServer/ns8-core), offering:

- 🚀 **Full-featured mail server** - Send, receive, and manage emails
- 🔒 **Built-in security** - DKIM, SPF, and bounce handling
- 📊 **Comprehensive analytics** - Track deliveries, opens, and clicks
- 🌐 **Web-based interface** - Modern UI for mail management
- 🔧 **API access** - RESTful API for integration
- 📈 **High performance** - Built for scale and reliability

## 🚀 Quick Start

### Installation

Install the Postal module on your NethServer 8 instance:

```bash
add-module ghcr.io/geniusdynamics/postal:latest 1
```

**Example output:**
```json
{
  "module_id": "postal1", 
  "image_name": "postal", 
  "image_url": "ghcr.io/geniusdynamics/postal:latest"
}
```

### Configuration

Configure your Postal instance (assuming instance name is `postal1`):

```bash
api-cli run configure-module --agent module/postal1 --data - <<EOF
{
  "host": "postal.yourdomain.com",
  "http2https": true,
  "lets_encrypt": true
}
EOF
```

`host` is the only required field. Every other setting keeps its current
value when it is left out, so a request can change a single setting:

```bash
api-cli run configure-module --agent module/postal1 --data '{"host": "postal.yourdomain.com", "default_spam_threshold": 6}'
```

Then create the first Postal administrator:

```bash
runagent -m postal1 podman exec -it postal-app postal make-user
```

### Access

- **Web interface**: `https://<host>`, HTTPS only (Traefik terminates TLS)
- **SMTP**: the `smtp_port` of the node (default `2525`, use `25` to receive
  mail from the Internet), opened in the node firewall. STARTTLS uses the
  Traefik certificate of the SMTP host name.

## ⚙️ Settings

The Settings page of the module sets the options below; the same names are
the fields of `configure-module` and of `get-configuration`.

| Section | Fields | Postal option |
|---|---|---|
| Web interface | `host`, `lets_encrypt`, `http2https` | `postal.web_hostname` |
| SMTP server | `smtp_hostname` (empty: `host`), `smtp_port` (2525, 25, 587 or another), `smtp_tls`, `max_message_size` (MB), `smtp_log_connections` | `postal.smtp_hostname`, `smtp_server.*` |
| Delivery | `default_maximum_delivery_attempts`, `default_maximum_hold_expiry_days`, `default_suppression_list_automatic_removal_days`, `default_spam_threshold`, `default_spam_failure_threshold`, `helo_hostname`, `use_resent_sender_header` | `postal.*`, `dns.helo_hostname` |
| IP pools | `use_ip_pools` | `POSTAL_USE_IP_POOLS` |
| Relays | `smtp_relays` (`[{"host", "port", "ssl_mode": "Auto/STARTTLS/TLS/None"}]`), `relay_via_cluster_smarthost`, `cluster_relay_provider` | `POSTAL_SMTP_RELAYS` |
| E-mails of Postal | `app_smtp_mode` (`smarthost`: the NS8 cluster smarthost, or `custom`), `app_smtp_host`, `app_smtp_port`, `app_smtp_username`, `app_smtp_password` (write-only), `app_smtp_tls`, `app_smtp_tls_verify`, `from_name`, `from_address` | `smtp.*` |
| OpenID Connect | `oidc_enabled`, `oidc_name`, `oidc_issuer`, `oidc_identifier`, `oidc_secret` (write-only), `oidc_scopes`, `oidc_uid_field`, `oidc_email_address_field`, `oidc_name_field`, `oidc_discovery`, `oidc_authorization_endpoint`, `oidc_token_endpoint`, `oidc_userinfo_endpoint`, `oidc_jwks_uri`, `oidc_local_authentication_enabled` | `OIDC_*` |
| Spam and virus checks | `rspamd_enabled`, `rspamd_host`, `rspamd_port`, `rspamd_ssl`, `rspamd_password` (write-only), `spamd_enabled`, `spamd_host`, `spamd_port`, `clamav_enabled`, `clamav_host`, `clamav_port` | `rspamd.*`, `spamd.*`, `clamav.*` |
| DNS names | `dns_mx_records`, `dns_spf_include`, `dns_return_path_domain`, `dns_route_domain`, `dns_track_domain` (empty: derived from `host`) | `dns.*` |
| Optional containers | `worker_host_network`, `rspamd_container`, `rspamd_webui`, `clamav_container` | `rspamd.*`, `clamav.*` |
| Performance and logs | `web_server_max_threads`, `worker_threads`, `main_db_pool_size`, `logging_enabled`, `smtp_log_connections`, `rails_log_enabled` | `web_server.*`, `worker.*`, `main_db.pool_size`, `logging.*` |

Secrets are write-only: `get-configuration` returns `oidc_secret_set`,
`app_smtp_password_set`, `rspamd_password_set` and `sentry_dsn_set`
instead of the values. They are stored in `state/secrets/secrets.env` (mode
0600) and reach the containers through `postal.env` (0600) as environment
variables, never through the module environment (Redis) or `postal.yml`.
The signing key and the TLS key reach the containers as podman secrets.

### CLI-only options

These options have no field on the Settings page; set them with
`configure-module`:

| Field | Postal option | Example |
|---|---|---|
| `trusted_proxies` | `postal.trusted_proxies` | `["10.0.0.0/8"]` |
| `allowed_request_destinations` | `postal.allowed_request_destinations` (webhooks to private addresses) | `["10.5.4.0/24", "hooks.lan"]` |
| `use_local_ns_for_domain_verification` | `postal.use_local_ns_for_domain_verification` | `true` |
| `batch_queued_messages`, `queued_message_lock_stale_days` | `postal.*` | `true`, `1` |
| `smtp_client_open_timeout`, `smtp_client_read_timeout` | `smtp_client.*` (seconds) | `30` |
| `dns_dkim_identifier`, `dns_custom_return_path_prefix`, `dns_domain_verify_prefix` | `dns.*` | `"postal"` |
| `rspamd_flags` | `rspamd.flags` | `"..."` |
| `gelf_host`, `gelf_port`, `gelf_facility` | `gelf.*` (logs to Graylog) | `"graylog.lan"` |
| `sentry_dsn` (write-only) | `logging.sentry_dsn` | `"https://..."` |

```bash
api-cli run configure-module --agent module/postal1 --data - <<EOF
{
  "host": "postal.yourdomain.com",
  "allowed_request_destinations": ["10.5.4.0/24"],
  "gelf_host": "graylog.yourdomain.com",
  "smtp_relays": [{"host": "relay.yourdomain.com", "port": 587, "ssl_mode": "STARTTLS"}]
}
EOF
```

Read the generated configuration (no secrets) with:

```bash
runagent -m postal1 podman exec postal-app cat /config/postal.yml
```

### Set by the module

`web_protocol` (https), the web server bind address and port (pod port
5000, published on `127.0.0.1:${TCP_PORT}` for Traefik), the SMTP server
port inside the pod (25), the health server ports, the MariaDB connection
(`main_db.*`, `message_db.*`, root credentials of the pod database),
`rails.environment` (production), `rails.secret_key`, `signing_key_path`,
the TLS certificate paths and `migration_waiter`.

### NS8 limits

- **IP pools**: Postal binds the source address of an IP pool for the
  outgoing connections. In the rootless pod (default) the network gives it
  only the primary address of the node (pasta) or a private one
  (slirp4netns): a pool with another address makes the deliveries fail
  with a connection error. With `worker_host_network` the worker, which
  delivers the messages, runs outside the pod with `--network=host`, still
  rootless, and can bind every address of the node. It reaches MariaDB
  through its unix socket (the `mysqld-run` volume), so no database port is
  opened; the optional rspamd and ClamAV are published for it on
  `127.0.0.2` and `127.0.0.3` with the module TCP port, its health server
  answers on `127.0.0.4`. **Tradeoff**: the worker then shares the loopback
  interface of the node and can reach the services listening on its
  127.0.0.1 (other modules); Postal still refuses webhooks to private and
  loopback addresses unless `allowed_request_destinations` lists them. The
  Settings page lists the node addresses; the pools are created in the
  Postal web interface.
- **Relays**: Postal relays have no SMTP authentication. A relay, or the
  NS8 cluster smarthost used as relay, must accept the messages from the
  address of the node. An authenticated cluster smarthost is refused as
  relay; it can still send the e-mails of Postal itself
  (`app_smtp_mode: smarthost`), which support authentication but not
  implicit TLS (port 465). Postal 3.3 spells its STARTTLS relay mode
  `STARTLS`: the module writes that spelling in `postal.yml` for the
  `STARTTLS` mode, otherwise Postal would send without encryption.
- **Cluster smarthost provider**: with `cluster_relay_provider`, Postal is
  listed in the NS8 Email notifications settings. NS8 sends to port 25
  without authentication, so it requires `smtp_port: 25` and an "SMTP-IP"
  credential for the cluster network in a Postal mail server.
- **OIDC**: register `https://<host>/auth/oidc/callback` as redirect URI in
  the provider. The Settings page offers the Keycloak, authentik and ZITADEL
  modules of the cluster as presets: complete the issuer with the realm or
  application. With discovery, Postal must reach the issuer over HTTPS with
  a trusted certificate. Local logins can be disabled only while OIDC is
  enabled.
- **SMTP port**: port 25 and the other mail ports cannot be shared with the
  Mail, mailcow or KumoMTA modules of the same node; configure-module
  refuses a port they use.
- **Track domains**: every track domain of the Postal mail servers
  (`<name>.<domain>`, a CNAME to the `dns_track_domain`) gets its own
  Traefik route, `<module>-track-<name>`, with the `X-Postal-Track-Host`
  header Postal expects and Let's Encrypt when `lets_encrypt` is on.
  `postal-track-routes.timer` adds and removes them every 5 minutes, and
  configure-module at once. A name already routed by another module is
  skipped. The Settings page lists each name with its certificate status.
- **Spam and virus checks**: `rspamd_container` runs rspamd in the pod
  (off by default) and points Postal to it; `rspamd_webui` publishes its
  web interface on `https://<host>/rspamd` (Traefik route
  `<module>-rspamd`). The controller password is generated in
  `state/rspamd.env` (0600, backed up); the Settings page shows it through
  the `reveal-rspamd-password` action, which the reader role cannot run.
  The controller trusts no address (`secure_ip`): Traefik connects from the
  loopback, so the password is asked for every request. `clamav_container`
  runs ClamAV in the pod (off by default); it needs about 1 GB of memory
  and downloads its signatures before it answers. Both images are pulled
  with the module even when they stay off. Without them, point Postal to
  existing rspamd, SpamAssassin or ClamAV services.
- Retention, message size per server, click and open tracking are settings
  of each Postal mail server, in the Postal web interface. Truemail is not
  part of Postal.

### What a change restarts

configure-module restarts only the containers that read a changed part of
the configuration: an OIDC change restarts the web server, a spam check
change the worker, a certificate the SMTP server. A new SMTP port creates
the pod again (every container, MariaDB included), as do updates.

### Upgrading from an older release

The update keeps every value and moves the instance to the current layout:
`settings.json`, the secrets in `secrets/` (the Rails secret key and the
signing key are kept), the credentials of the e-mails of Postal. Older
releases ran Postal in the Rails `test` environment, where e-mails are not
sent and CSRF protection is off: the update switches to `production`.
Caddy, unused, is removed. The schema migrations of a new Postal image run
with `postal upgrade` on every update.

## 🔧 Management Commands

### Get Current Configuration

```bash
api-cli run get-configuration --agent module/postal1
```

### Update Module

```bash
api-cli run update-module --data '{
  "module_url": "ghcr.io/geniusdynamics/postal:latest",
  "instances": ["postal1"],
  "force": true
}'
```

### Uninstall

```bash
remove-module --no-preserve postal1
```

## 🏗️ Architecture

### Services

The module deploys the following containerized services:

- **postal-app**: Main Postal application server
- **postal-smtp-app**: SMTP server, receives messages and incoming mail
- **postal-worker-app**: Background worker for processing tasks
- **mariadb-app**: Database backend

### Network Configuration

- **Port 5000** of the pod: web interface, published on `127.0.0.1:${TCP_PORT}` for Traefik
- **Port 25** of the pod: SMTP server, published on `smtp_port` of the node (default 2525)

### Backup

The backup holds `settings.json`, `secrets/` (signing key, Rails secret key,
write-only secrets), `database.env` and `postal.sql`, a dump of every Postal
database (the main one and the message database of each mail server).
Restore and clone apply every setting again, with Let's Encrypt off: enable
it again once the DNS points to the node.

## 🔍 Advanced Configuration

### Smarthost Integration

Postal follows the NS8 [smarthost configuration](https://nethserver.github.io/ns8-core/core/smarthost/):
with `app_smtp_mode: smarthost` (the default) it sends its own e-mails
through it, and with `relay_via_cluster_smarthost` all the outgoing mail.
The `smarthost-changed` event renders the configuration again.

### Configuration files

`configure-module` renders `state/postal.yml` (no secrets) and
`state/postal.env` (0600, secrets as environment variables) from
`state/settings.json`, in `imageroot/pypkg/postal_ns8.py`. Do not edit them:
changes are lost.

## 🛠️ Development & Debugging

### Debug Commands

1. **Check general environment state:**
   ```bash
   runagent -m env
   ```

2. **Check instance environment variables:**
   ```bash
   runagent -m postal1 env
   ```

3. **Enter agent environment:**
   ```bash
   runagent -m postal1
   ```

4. **View running containers:**
   ```bash
   runagent -m postal1
   podman ps
   ```

5. **Access container shell:**
   ```bash
   runagent -m postal1 podman exec -it postal-app /bin/bash
   ```

   Inside the container, you can run:
   - **Create or migrate the database** (never run `postal initialize` on
     a database in use: it replaces the tables). Outside the container:
     `api-cli run module/postal1/initialize-postal`
   - **Create a new user:**
     ```bash
     postal make-user
     ```
   - **View configuration:**
     ```bash
     cat /config/postal.yml
     ```

6. **Inspect container environment** (prints the secrets of `postal.env`):
   ```bash
   podman exec postal-app env
   ```

7. **Access container shell in sh:**
   ```bash
   podman exec -ti postal-app sh
   ```

   Check specific configurations with:
   ```bash
   cat /config/postal.yml
   ```

   These commands are essential for debugging and managing the Postal instance effectively.

### Project Structure

```
ns8-postal/
├── imageroot/                 # Module runtime files
│   ├── actions/              # Module actions (configure, restore, etc.)
│   ├── bin/                  # Utility scripts
│   ├── events/               # Event handlers
│   ├── systemd/              # Systemd service definitions
│   └── templates/            # Configuration templates
├── ui/                       # Web interface
│   ├── src/                  # Vue.js application source
│   └── public/               # Static assets and metadata
├── tests/                    # Automated tests
└── build-images.sh          # Image building script
```

## 🧪 Testing

Run the automated test suite:

```bash
./test-module.sh <NODE_ADDR> ghcr.io/geniusdynamics/postal:latest
```

Tests are implemented using [Robot Framework](https://robotframework.org/) and cover:
- Module installation and configuration
- Service health checks
- Basic functionality validation

### Manual Testing

1. **Verify services are running:**
   ```bash
   runagent -m postal1
   systemctl --user status postal.service
   ```

2. **Check logs:**
   ```bash
   podman logs postal-app
   ```

## 🌍 Internationalization

The module supports multiple languages through [Weblate](https://hosted.weblate.org/projects/ns8/).

**Supported Languages:**
- English (en)
- German (de)
- Spanish (es)
- Italian (it)
- Portuguese (pt, pt_BR)
- Basque (eu)

**Contributing Translations:**
1. Join the [NethServer Weblate project](https://hosted.weblate.org/projects/ns8/)
2. Add translations for the `postal` component
3. Submit pull requests for new language files

## 📚 Documentation

- **Postal Documentation**: [docs.postalserver.io](https://docs.postalserver.io/)
- **NethServer 8 Core**: [ns8-core documentation](https://nethserver.github.io/ns8-core/)
- **Module API Reference**: Auto-generated from code comments

## 🤝 Contributing

We welcome contributions! Please see our [contribution guidelines](CONTRIBUTING.md) for details.

### Development Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/geniusdynamics/ns8-postal.git
   cd ns8-postal
   ```

2. **Build development images:**
   ```bash
   ./build-images.sh
   ```

3. **Run tests:**
   ```bash
   ./test-module.sh localhost:9999 postal:latest
   ```

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/geniusdynamics/dev/issues)
- **Documentation**: [Postal Documentation](https://docs.postalserver.io/)
- **Community**: [NethServer Community](https://community.nethserver.org/)
- **Commercial Support**: [support@genius.ke](mailto:support@genius.ke)

## 📄 License

This project is licensed under the [GNU General Public License v3.0](LICENSE).

```
Copyright (C) 2023 Genius Dynamics

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
```

## 👥 Authors

- **Genius Dynamics** - [support@genius.ke](mailto:support@genius.ke)
- **NethServer Community** - [community.nethserver.org](https://community.nethserver.org/)

---

<div align="center">
  Made with ❤️ by the <a href="https://github.com/geniusdynamics">Genius Dynamics</a> team<br>
  Powered by <a href="https://github.com/NethServer/ns8-core">NethServer 8</a>
</div>
