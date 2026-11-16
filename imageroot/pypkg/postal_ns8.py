#
# Copyright (C) 2026 Genius Dynamics
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Shared code of the ns8-postal actions, events and helpers.

Files of the state directory (the working directory of the actions and
of the systemd units):

- settings.json: every setting, no secrets (backed up)
- secrets/secrets.env: 0600, RAILS_SECRET_KEY, OIDC_SECRET, SMTP_PASSWORD,
  RSPAMD_PASSWORD, LOGGING_SENTRY_DSN (backed up)
- secrets/signing.key: 0600, the Postal signing key (backed up)
- database.env: 0600, MariaDB passwords (backed up)
- postal.yml: the rendered Postal configuration, no secrets (rendered again
  by configure-module)
- postal.env: 0600, the rendered secrets, passed with podman --env-file:
  Postal reads environment variables over postal.yml
- tls/: certificate of the SMTP host name from Traefik (get-certificate)

The containers run Postal as the uid 999 of the image: the signing key and
the TLS key reach them as podman secrets (bin/postal-secrets), owned by
999, mode 0400, under /run/secrets.
"""

import copy
import ipaddress
import json
import os
import re
import secrets
import subprocess
import sys

import agent

SETTINGS_FILE = "settings.json"
SECRETS_DIR = "secrets"
SECRETS_ENV = "secrets/secrets.env"
SIGNING_KEY = "secrets/signing.key"
DATABASE_ENV = "database.env"
POSTAL_YML = "postal.yml"
POSTAL_ENV = "postal.env"
WORKER_ENV = "postal-worker.env"     # 0600, extra variables of the worker
RSPAMD_DIR = "rspamd"                # files mounted in the rspamd container
RSPAMD_CONTROLLER_FILE = "rspamd/worker-controller.inc"
RSPAMD_ENV = "rspamd.env"            # 0600, RSPAMD_adminpw; ConditionPathExists of rspamd-app.service
RSPAMD_ROUTE_STATE = ".rspamd-route.json"
CLAMAV_FLAG = ".clamav-enabled"      # ConditionPathExists of clamav-app.service

# The pod publishes the rspamd controller and clamd of the optional
# containers on 127.0.0.1 of the node, on the second and third TCP ports of
# the module (TCP_PORTS; an install older than tcp-ports-demand=3 gets them
# from the node agent, POSTAL_EXTRA_TCP_PORTS). pasta forwards a host port
# to one pod port only, whatever the address: they need ports of their own.
# The worker of the host network runs its health server on 127.0.0.4 with
# the web TCP port, which the pod publishes on 127.0.0.1 only.
RSPAMD_PATH = "/rspamd"              # web UI path on the Postal host name
WORKER_HEALTH_LOOPBACK = "127.0.0.4" # health server of the host-network worker
TLS_DIR = "tls"
TLS_CERT = "tls/cert.pem"
TLS_KEY = "tls/key.pem"
TRACK_ROUTES_STATE = "track-routes.json"

# Paths inside the containers
C_SECRETS = "/run/secrets"

HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
FIELD_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
SCOPE_RE = re.compile(r"^[A-Za-z0-9_.:/-]{1,128}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

RELAY_SSL_MODES = ["Auto", "STARTTLS", "TLS", "None"]
APP_SMTP_MODES = ["smarthost", "custom"]
APP_SMTP_TLS = ["starttls_auto", "starttls", "none"]

# Ports used by the other NS8 mail modules of the node
MAIL_MODULE_PORTS = {
    "mail": [25, 110, 143, 465, 587, 993, 995, 4190],
    "mailcow": [25, 110, 143, 465, 587, 993, 995, 4190],
}

# OIDC providers among the NS8 modules (image name -> kind)
OIDC_MODULES = {
    "keycloak": "keycloak",
    "goauthentik": "authentik",
    "authentik": "authentik",
    "zitadel": "zitadel",
}

DEFAULTS = {
    # Web interface (Traefik)
    "host": "",
    "http2https": True,
    "lets_encrypt": False,
    # SMTP server
    "smtp_hostname": "",              # empty: the host name of the web interface
    "smtp_port": 2525,                # node port published to the pod port 25
    "smtp_tls": True,                 # STARTTLS with the Traefik certificate
    "max_message_size": 14,           # MB
    "smtp_log_connections": False,
    # Delivery
    "use_ip_pools": False,
    "default_maximum_delivery_attempts": 18,
    "default_maximum_hold_expiry_days": 7,
    "default_suppression_list_automatic_removal_days": 30,
    "default_spam_threshold": 5,
    "default_spam_failure_threshold": 20,
    "use_resent_sender_header": True,
    "helo_hostname": "",
    "batch_queued_messages": True,
    "queued_message_lock_stale_days": 1,
    "smtp_client_open_timeout": 30,
    "smtp_client_read_timeout": 30,
    # Relays of the outgoing mail
    "smtp_relays": [],                # [{host, port, ssl_mode}]
    "relay_via_cluster_smarthost": False,
    # Smarthost provider of the cluster
    "cluster_relay_provider": False,
    # E-mails of Postal itself (password resets, invitations...)
    "app_smtp_mode": "smarthost",
    "app_smtp_host": "",
    "app_smtp_port": 587,
    "app_smtp_username": "",
    "app_smtp_tls": "starttls_auto",
    "app_smtp_tls_verify": True,
    "from_name": "Postal",
    "from_address": "",
    # OpenID Connect
    "oidc_enabled": False,
    "oidc_name": "OIDC Provider",
    "oidc_issuer": "",
    "oidc_identifier": "",
    "oidc_scopes": ["openid", "email"],
    "oidc_uid_field": "sub",
    "oidc_email_address_field": "email",
    "oidc_name_field": "name",
    "oidc_discovery": True,
    "oidc_authorization_endpoint": "",
    "oidc_token_endpoint": "",
    "oidc_userinfo_endpoint": "",
    "oidc_jwks_uri": "",
    "oidc_local_authentication_enabled": True,
    # Message inspection
    "rspamd_enabled": False,
    "rspamd_host": "",
    "rspamd_port": 11334,
    "rspamd_ssl": False,
    "rspamd_flags": "",
    "spamd_enabled": False,
    "spamd_host": "",
    "spamd_port": 783,
    "clamav_enabled": False,
    "clamav_host": "",
    "clamav_port": 3310,
    # DNS names given to the users of Postal (empty: derived from the host)
    "dns_mx_records": [],
    "dns_spf_include": "",
    "dns_return_path_domain": "",
    "dns_route_domain": "",
    "dns_track_domain": "",
    "dns_dkim_identifier": "postal",
    "dns_custom_return_path_prefix": "psrp",
    "dns_domain_verify_prefix": "postal-verification",
    "use_local_ns_for_domain_verification": False,
    # Processes
    "web_server_max_threads": 5,
    "worker_threads": 2,
    "main_db_pool_size": 5,
    # Logging
    "logging_enabled": True,
    "rails_log_enabled": False,
    "gelf_host": "",
    "gelf_port": 12201,
    "gelf_facility": "postal",
    # Advanced
    "trusted_proxies": [],
    "allowed_request_destinations": [],
    # Optional containers and worker network
    "worker_host_network": False,     # worker outside the pod, --network=host (IP pools)
    "rspamd_container": False,        # rspamd in the pod, used by Postal
    "rspamd_webui": False,            # https://<host>/rspamd through Traefik
    "clamav_container": False,        # ClamAV in the pod, used by Postal (~1 GB RAM)
}

# Write-only secrets: configure-module field -> secrets.env variable
SECRET_FIELDS = {  # rspamd controller password: generated, see rspamd_password()
    "oidc_secret": "OIDC_SECRET",
    "app_smtp_password": "SMTP_PASSWORD",
    "rspamd_password": "RSPAMD_PASSWORD",
    "sentry_dsn": "LOGGING_SENTRY_DSN",
}

INT_FIELDS = [k for k, v in DEFAULTS.items() if isinstance(v, int) and not isinstance(v, bool)]
BOOL_FIELDS = [k for k, v in DEFAULTS.items() if isinstance(v, bool)]
LIST_FIELDS = [k for k, v in DEFAULTS.items() if isinstance(v, list)]


def log(message):
    print(message, file=sys.stderr)


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------

def write_file(path, content, mode=0o644):
    """Atomic write; returns True if the content changed"""
    if isinstance(content, str):
        content = content.encode()
    try:
        with open(path, "rb") as fp:
            if fp.read() == content:
                if (os.stat(path).st_mode & 0o777) != mode:
                    os.chmod(path, mode)
                return False
    except FileNotFoundError:
        pass
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as fp:
        fp.write(content)
    os.chmod(tmp, mode)
    os.replace(tmp, path)
    return True


def read_env(path):
    try:
        return agent.read_envfile(path)
    except FileNotFoundError:
        return {}


def write_env(path, envmap, mode=0o600):
    os.makedirs(os.path.dirname(path) or ".", mode=0o700, exist_ok=True)
    payload = "".join(f"{k}={envmap[k]}\n" for k in sorted(envmap) if envmap[k] is not None)
    return write_file(path, payload, mode)


def read_secrets():
    return read_env(SECRETS_ENV)


def write_secrets(envmap):
    os.makedirs(SECRETS_DIR, mode=0o700, exist_ok=True)
    os.chmod(SECRETS_DIR, 0o700)
    return write_env(SECRETS_ENV, envmap)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------

def load_settings():
    settings = copy.deepcopy(DEFAULTS)
    try:
        with open(SETTINGS_FILE) as fp:
            stored = json.load(fp)
        settings.update({k: v for k, v in stored.items() if k in DEFAULTS})
    except FileNotFoundError:
        # Not configured yet, or an install older than settings.json
        settings.update(legacy_settings())
    return settings


def save_settings(settings):
    clean = {k: settings[k] for k in DEFAULTS}
    write_file(SETTINGS_FILE, json.dumps(clean, indent=2, sort_keys=True) + "\n", 0o644)


def coerce(settings):
    """Normalize the types of the values received from the UI or the CLI"""
    for key in INT_FIELDS:
        try:
            settings[key] = int(settings[key])
        except (TypeError, ValueError):
            pass
    for key in BOOL_FIELDS:
        if isinstance(settings[key], str):
            settings[key] = settings[key].lower() in ("1", "true", "yes", "on")
    for key in LIST_FIELDS:
        if isinstance(settings[key], str):
            settings[key] = [x.strip() for x in re.split(r"[,\s]+", settings[key]) if x.strip()]
    for key in ("host", "smtp_hostname", "helo_hostname", "dns_spf_include", "dns_return_path_domain",
                "dns_route_domain", "dns_track_domain"):
        if isinstance(settings[key], str):
            settings[key] = settings[key].strip().lower().rstrip(".")
    settings["dns_mx_records"] = [x.lower().rstrip(".") for x in settings["dns_mx_records"]]
    relays = []
    for relay in settings["smtp_relays"] or []:
        if isinstance(relay, str):
            relay = parse_relay_url(relay)
        relays.append({
            "host": str(relay.get("host", "")).strip().lower(),
            "port": int(relay.get("port") or 25),
            "ssl_mode": {"STARTLS": "STARTTLS"}.get(relay.get("ssl_mode"), relay.get("ssl_mode") or "Auto"),
        })
    settings["smtp_relays"] = relays
    return settings


def parse_relay_url(value):
    """smtp://host:port?ssl_mode=X, the format of POSTAL_SMTP_RELAYS"""
    from urllib.parse import urlparse, parse_qs
    url = urlparse(value if "://" in value else "smtp://" + value)
    query = parse_qs(url.query)
    return {"host": url.hostname or "", "port": url.port or 25,
            "ssl_mode": (query.get("ssl_mode") or ["Auto"])[0]}


def configure_payload(settings, lets_encrypt=False):
    """configure-module input with every setting: restore and clone pass it
    with Let's Encrypt off, the DNS may not point to this node yet"""
    data = {k: copy.deepcopy(settings[k]) for k in DEFAULTS}
    data["lets_encrypt"] = lets_encrypt
    return data


def smtp_hostname(settings):
    return settings["smtp_hostname"] or settings["host"]


def dns_names(settings):
    """The DNS names Postal shows to its users, derived from the host"""
    host = settings["host"] or "postal.example.com"
    return {
        "mx_records": settings["dns_mx_records"] or [smtp_hostname(settings) or host],
        "spf_include": settings["dns_spf_include"] or f"spf.{host}",
        "return_path_domain": settings["dns_return_path_domain"] or f"rp.{host}",
        "route_domain": settings["dns_route_domain"] or f"routes.{host}",
        "track_domain": settings["dns_track_domain"] or f"track.{host}",
    }


def oidc_redirect_uri(settings):
    return f"https://{settings['host']}/auth/oidc/callback" if settings["host"] else ""


# --------------------------------------------------------------------------
# Legacy installs (before settings.json)
# --------------------------------------------------------------------------

def legacy_settings():
    """Settings of an install configured by an older release: the Traefik
    variables of the environment and state/postal.env"""
    found = {}
    if os.environ.get("TRAEFIK_HOST"):
        found["host"] = os.environ["TRAEFIK_HOST"]
        found["http2https"] = os.environ.get("TRAEFIK_HTTP2HTTPS", "True").lower() == "true"
        found["lets_encrypt"] = os.environ.get("TRAEFIK_LETS_ENCRYPT", "False").lower() == "true"
    old = read_env(POSTAL_ENV) if not os.path.exists(SECRETS_ENV) else {}
    if old.get("FROMNAME"):
        found["from_name"] = old["FROMNAME"]
    if old.get("FROMADDRESS"):
        found["from_address"] = old["FROMADDRESS"]
    if old.get("USERNAME"):
        # The old release sent the e-mails of Postal to its own SMTP server
        # with these credentials (on a port that was wrong inside the pod)
        found["app_smtp_mode"] = "custom"
        found["app_smtp_host"] = "127.0.0.1"
        found["app_smtp_port"] = 25
        found["app_smtp_username"] = old["USERNAME"]
        found["app_smtp_tls"] = "none"
    if os.environ.get("POSTAL_SMTP_PORT"):
        found["smtp_port"] = int(os.environ["POSTAL_SMTP_PORT"])
    return found


def migrate_legacy():
    """Move the files of an older release to the current layout, keeping
    every value: the settings, the Rails secret key, the signing key, the
    password of the e-mails of Postal. Returns True if something moved."""
    if os.path.exists(SETTINGS_FILE) and os.path.exists(SECRETS_ENV) and os.path.exists(SIGNING_KEY):
        return False
    changed = False
    old_postal = read_env(POSTAL_ENV) if not os.path.exists(SECRETS_ENV) else {}
    appdb = read_env("app-db.env")
    if not os.path.exists(SETTINGS_FILE) and (os.environ.get("TRAEFIK_HOST") or old_postal):
        save_settings(load_settings())
        changed = True
    if not os.path.exists(SECRETS_ENV):
        sec = {"RAILS_SECRET_KEY": appdb.get("SECRETKEY") or secrets.token_hex(64)}
        if old_postal.get("USERNAME") and old_postal.get("PASSWORD"):
            sec["SMTP_PASSWORD"] = old_postal["PASSWORD"]
        write_secrets(sec)
        changed = True
    if not os.path.exists(SIGNING_KEY):
        os.makedirs(SECRETS_DIR, mode=0o700, exist_ok=True)
        if os.path.exists("config/signing.key"):
            with open("config/signing.key", "rb") as fp:
                write_file(SIGNING_KEY, fp.read(), 0o600)
        else:
            generate_signing_key()
        changed = True
    # Files of the old layout
    for name in ("app-db.env", "Caddyfile", "smarthost.env", "config/postal.yml", "config/signing.key"):
        try:
            os.unlink(name)
            changed = True
        except FileNotFoundError:
            pass
        except IsADirectoryError:
            pass
    try:
        os.rmdir("config")
    except OSError:
        pass
    if os.path.exists(DATABASE_ENV):
        os.chmod(DATABASE_ENV, 0o600)
    return changed


def generate_signing_key():
    os.makedirs(SECRETS_DIR, mode=0o700, exist_ok=True)
    tmp = SIGNING_KEY + ".tmp"
    old = os.umask(0o077)
    try:
        subprocess.run(["openssl", "genrsa", "-out", tmp, "2048"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.umask(old)
    os.chmod(tmp, 0o600)
    os.replace(tmp, SIGNING_KEY)


# --------------------------------------------------------------------------
# Cluster
# --------------------------------------------------------------------------

def smarthost():
    try:
        rdb = agent.redis_connect(use_replica=True)
        return agent.get_smarthost_settings(rdb)
    except Exception as ex:
        log(agent.SD_WARNING + f"Cannot read the cluster smarthost: {ex}")
        return {"enabled": False, "host": "", "port": 587, "username": "", "password": "",
                "encrypt_smtp": "starttls", "tls_verify": True}


def depends_on_smarthost(settings):
    return settings["app_smtp_mode"] == "smarthost" or settings["relay_via_cluster_smarthost"]


def cluster_info():
    """(cluster network CIDR, node VPN address) from Redis"""
    try:
        rdb = agent.redis_connect(use_replica=True)
        network = rdb.get("cluster/network") or ""
        address = rdb.hget(f"node/{os.environ['NODE_ID']}/vpn", "ip_address") or ""
        return network, address
    except Exception as ex:
        log(agent.SD_WARNING + f"Cannot read the cluster network: {ex}")
        return "", ""


def image_name(image_url):
    return (image_url or "").rsplit("/", 1)[-1].split(":", 1)[0].split("@", 1)[0]


def modules_by_image(rdb, names, same_node=False):
    """{module_id: image_name} of the modules whose image is in names"""
    found = {}
    node_id = os.environ.get("NODE_ID")
    for module_id, mnode in (rdb.hgetall("cluster/module_node") or {}).items():
        if module_id == os.environ.get("MODULE_ID"):
            continue
        if same_node and str(mnode) != str(node_id):
            continue
        name = image_name(rdb.hget(f"module/{module_id}/environment", "IMAGE_URL"))
        if name in names:
            found[module_id] = name
    return found


def ports_taken_on_node():
    """{port: module_id} of the SMTP ports used by the other mail modules
    of this node"""
    rdb = agent.redis_connect(use_replica=True)
    taken = {}
    for module_id, name in modules_by_image(rdb, list(MAIL_MODULE_PORTS) + ["kumomta", "postal"], True).items():
        if name in MAIL_MODULE_PORTS:
            ports = MAIL_MODULE_PORTS[name]
        else:
            renv = rdb.hgetall(f"module/{module_id}/environment") or {}
            keys = ["KUMO_INBOUND_PORT", "KUMO_SUBMISSION_PORT"] if name == "kumomta" else ["POSTAL_SMTP_PORT"]
            ports = []
            for key in keys:
                if renv.get(key):
                    ports.append(int(renv[key]))
            if name == "postal" and not ports:
                ports = [2525]
        for port in ports:
            taken[int(port)] = module_id
    return taken


def oidc_providers():
    """OIDC-capable NS8 modules of the cluster, with an issuer hint"""
    rdb = agent.redis_connect(use_replica=True)
    providers = []
    for module_id, name in sorted(modules_by_image(rdb, list(OIDC_MODULES)).items()):
        renv = rdb.hgetall(f"module/{module_id}/environment") or {}
        host = renv.get("TRAEFIK_HOST", "")
        if not host:
            continue
        kind = OIDC_MODULES[name]
        if kind == "keycloak":
            issuer = f"https://{host}/realms/<realm>"
        elif kind == "authentik":
            issuer = f"https://{host}/application/o/<application-slug>/"
        else:
            issuer = f"https://{host}"
        providers.append({
            "module_id": module_id,
            "kind": kind,
            "host": host,
            "ui_name": rdb.get(f"module/{module_id}/ui_name") or "",
            "issuer": issuer,
            "name": {"keycloak": "Keycloak", "authentik": "authentik", "zitadel": "ZITADEL"}[kind],
        })
    return providers


def node_addresses():
    """Global unicast addresses of the node interfaces"""
    try:
        out = subprocess.run(["ip", "-j", "addr", "show"], capture_output=True, text=True, check=True).stdout
        links = json.loads(out)
    except Exception as ex:
        log(agent.SD_WARNING + f"Cannot list the node addresses: {ex}")
        return []
    found = []
    for link in links:
        ifname = link.get("ifname", "")
        if ifname == "lo" or ifname.startswith(("wg", "cni", "podman", "veth", "tap")):
            continue
        for addr in link.get("addr_info", []):
            if addr.get("scope") != "global":
                continue
            ip = ipaddress.ip_address(addr["local"])
            found.append({
                "address": str(ip),
                "family": "ipv%d" % ip.version,
                "interface": ifname,
                "public": ip.is_global,
            })
    return found


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def yaml_value(value):
    """A YAML scalar or flow sequence, JSON-quoted: JSON is valid YAML"""
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return json.dumps(value)


# Postal 3.3 spells its STARTTLS mode "STARTLS" (SMTPClient::SSLModes): any
# other value disables encryption towards the relay
POSTAL_SSL_MODES = {"Auto": "Auto", "STARTTLS": "STARTLS", "TLS": "TLS", "None": "None"}


def relay_urls(settings, warnings):
    urls = [f"smtp://{r['host']}:{r['port']}?ssl_mode={POSTAL_SSL_MODES[r['ssl_mode']]}"
            for r in settings["smtp_relays"] if r["host"]]
    if settings["relay_via_cluster_smarthost"]:
        sh = smarthost()
        if not sh["enabled"] or not sh["host"]:
            warnings.append("cluster_smarthost_disabled")
        elif sh["username"]:
            # Postal relays have no SMTP AUTH: an authenticated smarthost
            # would refuse the messages
            warnings.append("cluster_smarthost_requires_auth")
        else:
            mode = {"starttls": "STARTLS", "tls": "TLS", "none": "None"}.get(sh["encrypt_smtp"], "Auto")
            urls.insert(0, f"smtp://{sh['host']}:{sh['port']}?ssl_mode={mode}")
    return urls


def app_smtp(settings, sec, warnings):
    """(smtp section, SMTP_PASSWORD) of the e-mails of Postal itself"""
    section = {
        "from_name": settings["from_name"] or "Postal",
        "from_address": settings["from_address"] or f"postal@{settings['host'] or 'example.com'}",
    }
    if settings["app_smtp_mode"] == "smarthost":
        sh = smarthost()
        if not sh["enabled"] or not sh["host"]:
            warnings.append("cluster_smarthost_disabled")
            section.update({"host": "127.0.0.1", "port": 25})
            return section, ""
        section.update({"host": sh["host"], "port": int(sh["port"])})
        if sh["username"]:
            section["username"] = sh["username"]
        enc = sh["encrypt_smtp"]
        section["enable_starttls"] = enc == "starttls"
        section["enable_starttls_auto"] = enc != "none"
        if enc == "tls":
            # ActionMailer cannot be told to use implicit TLS from postal.yml
            warnings.append("cluster_smarthost_implicit_tls")
        section["openssl_verify_mode"] = "peer" if sh["tls_verify"] else "none"
        return section, sh["password"] if sh["username"] else ""
    section.update({"host": settings["app_smtp_host"] or "127.0.0.1", "port": int(settings["app_smtp_port"])})
    if settings["app_smtp_username"]:
        section["username"] = settings["app_smtp_username"]
    section["enable_starttls"] = settings["app_smtp_tls"] == "starttls"
    section["enable_starttls_auto"] = settings["app_smtp_tls"] != "none"
    section["openssl_verify_mode"] = "peer" if settings["app_smtp_tls_verify"] else "none"
    return section, sec.get("SMTP_PASSWORD", "") if settings["app_smtp_username"] else ""


def render(settings, mark=True):
    """Write postal.yml and postal.env; returns (affected containers,
    warnings). The affected containers are the Postal processes that read
    a changed section or variable (RESTART_MAP); they are also added to the
    restart set of configure-module."""
    warnings = []
    sec = read_secrets()
    db = read_env(DATABASE_ENV)
    dns = dns_names(settings)
    host = settings["host"] or "postal.example.com"
    tls_ready = settings["smtp_tls"] and os.path.exists(TLS_CERT) and os.path.exists(TLS_KEY)

    smtp_section, smtp_password = app_smtp(settings, sec, warnings)

    conf = {
        "postal": {
            "web_hostname": host,
            "web_protocol": "https",
            "smtp_hostname": smtp_hostname(settings) or host,
            "use_ip_pools": settings["use_ip_pools"],
            "default_maximum_delivery_attempts": settings["default_maximum_delivery_attempts"],
            "default_maximum_hold_expiry_days": settings["default_maximum_hold_expiry_days"],
            "default_suppression_list_automatic_removal_days": settings["default_suppression_list_automatic_removal_days"],
            "default_spam_threshold": settings["default_spam_threshold"],
            "default_spam_failure_threshold": settings["default_spam_failure_threshold"],
            "use_local_ns_for_domain_verification": settings["use_local_ns_for_domain_verification"],
            "use_resent_sender_header": settings["use_resent_sender_header"],
            "signing_key_path": f"{C_SECRETS}/signing.key",
            "smtp_relays": relay_urls(settings, warnings),
            "trusted_proxies": settings["trusted_proxies"],
            "allowed_request_destinations": settings["allowed_request_destinations"],
            "queued_message_lock_stale_days": settings["queued_message_lock_stale_days"],
            "batch_queued_messages": settings["batch_queued_messages"],
        },
        "web_server": {
            # Traefik reaches the pod port 5000 through the pod interface
            "default_bind_address": "0.0.0.0",
            "default_port": 5000,
            "max_threads": settings["web_server_max_threads"],
        },
        "worker": {
            "default_health_server_port": 9090,
            "default_health_server_bind_address": "127.0.0.1",
            "threads": settings["worker_threads"],
        },
        "main_db": {
            "host": "127.0.0.1",
            "port": 3306,
            "username": "root",
            "database": db.get("MARIADB_DATABASE", "postal"),
            "pool_size": settings["main_db_pool_size"],
            "encoding": "utf8mb4",
        },
        "message_db": {
            "host": "127.0.0.1",
            "port": 3306,
            "username": "root",
            "encoding": "utf8mb4",
            "database_name_prefix": db.get("MARIADB_DATABASE", "postal"),
        },
        "logging": {
            "enabled": settings["logging_enabled"],
            "rails_log_enabled": settings["rails_log_enabled"],
            "highlighting_enabled": False,
        },
        "gelf": {
            "port": settings["gelf_port"],
            "facility": settings["gelf_facility"],
        },
        "smtp_server": {
            "default_port": 25,
            "default_bind_address": "::",
            "default_health_server_port": 9091,
            "default_health_server_bind_address": "127.0.0.1",
            "tls_enabled": bool(tls_ready),
            "tls_certificate_path": f"{C_SECRETS}/smtp.cert",
            "tls_private_key_path": f"{C_SECRETS}/smtp.key",
            "log_connections": settings["smtp_log_connections"],
            "max_message_size": settings["max_message_size"],
        },
        "dns": {
            "mx_records": dns["mx_records"],
            "spf_include": dns["spf_include"],
            "return_path_domain": dns["return_path_domain"],
            "route_domain": dns["route_domain"],
            "track_domain": dns["track_domain"],
            "dkim_identifier": settings["dns_dkim_identifier"],
            "domain_verify_prefix": settings["dns_domain_verify_prefix"],
            "custom_return_path_prefix": settings["dns_custom_return_path_prefix"],
        },
        "smtp": smtp_section,
        "rails": {
            "environment": "production",
        },
        "rspamd": {
            "enabled": settings["rspamd_enabled"],
            "host": settings["rspamd_host"] or "127.0.0.1",
            "port": settings["rspamd_port"],
            "ssl": settings["rspamd_ssl"],
        } if not settings["rspamd_container"] else {
            # The normal worker of the rspamd container of the pod
            "enabled": True,
            "host": "127.0.0.1",
            "port": 11333,
            "ssl": False,
        },
        "spamd": {
            "enabled": settings["spamd_enabled"],
            "host": settings["spamd_host"] or "127.0.0.1",
            "port": settings["spamd_port"],
        },
        "clamav": {
            "enabled": settings["clamav_enabled"],
            "host": settings["clamav_host"] or "127.0.0.1",
            "port": settings["clamav_port"],
        } if not settings["clamav_container"] else {
            "enabled": True,
            "host": "127.0.0.1",
            "port": 3310,
        },
        "smtp_client": {
            "open_timeout": settings["smtp_client_open_timeout"],
            "read_timeout": settings["smtp_client_read_timeout"],
        },
        "migration_waiter": {
            # Processes started before "postal upgrade" wait for it
            "enabled": True,
            "attempts": 120,
            "sleep_time": 2,
        },
        "oidc": {
            "enabled": settings["oidc_enabled"],
            "local_authentication_enabled": settings["oidc_local_authentication_enabled"] or not settings["oidc_enabled"],
            "name": settings["oidc_name"] or "OIDC Provider",
            "issuer": settings["oidc_issuer"],
            "identifier": settings["oidc_identifier"],
            "scopes": settings["oidc_scopes"] or ["openid", "email"],
            "uid_field": settings["oidc_uid_field"] or "sub",
            "email_address_field": settings["oidc_email_address_field"] or "email",
            "name_field": settings["oidc_name_field"] or "name",
            "discovery": settings["oidc_discovery"],
        },
    }
    if settings["helo_hostname"]:
        conf["dns"]["helo_hostname"] = settings["helo_hostname"]
    if settings["gelf_host"]:
        conf["gelf"]["host"] = settings["gelf_host"]
    if settings["rspamd_flags"] and not settings["rspamd_container"]:
        conf["rspamd"]["flags"] = settings["rspamd_flags"]
    if not settings["oidc_discovery"]:
        for key in ("authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri"):
            conf["oidc"][key] = settings["oidc_" + key]
    if settings["smtp_tls"] and not tls_ready:
        warnings.append("smtp_certificate_missing")

    lines = [
        "# Generated by configure-module of ns8-postal: do not edit, changes are lost.",
        "# The secrets are in postal.env (environment variables override this file).",
        "version: 2",
    ]
    for section, values in conf.items():
        lines.append("")
        lines.append(f"{section}:")
        for key, value in values.items():
            lines.append(f"  {key}: {yaml_value(value)}")
    write_file(POSTAL_YML, "\n".join(lines) + "\n", 0o644)

    env = {
        "MAIN_DB_PASSWORD": db.get("MARIADB_ROOT_PASSWORD", ""),
        "MESSAGE_DB_PASSWORD": db.get("MARIADB_ROOT_PASSWORD", ""),
        "RAILS_SECRET_KEY": sec.get("RAILS_SECRET_KEY", ""),
    }
    if settings["oidc_enabled"] and sec.get("OIDC_SECRET"):
        env["OIDC_SECRET"] = sec["OIDC_SECRET"]
    if smtp_password:
        env["SMTP_PASSWORD"] = smtp_password
    if settings["rspamd_enabled"] and not settings["rspamd_container"] and sec.get("RSPAMD_PASSWORD"):
        env["RSPAMD_PASSWORD"] = sec["RSPAMD_PASSWORD"]
    if sec.get("LOGGING_SENTRY_DSN"):
        env["LOGGING_SENTRY_DSN"] = sec["LOGGING_SENTRY_DSN"]
    write_env(POSTAL_ENV, env)
    render_rspamd(settings)
    render_clamav(settings)
    worker_env = render_worker_env(settings)
    write_env(WORKER_ENV, worker_env)
    affected = changed_containers(conf, env, {
        "worker_env": worker_env,
        "rspamd": rspamd_state(settings),
        "clamav": settings["clamav_container"],
        "pod_publish": pod_publish(settings),
        "worker_network": worker_network_args(settings),
    })
    if mark:
        mark_restart(affected)
    return affected, sorted(set(warnings))


# --------------------------------------------------------------------------
# Restart only what a change affects
# --------------------------------------------------------------------------

RENDERED_STATE = ".rendered.json"
RESTART_SET = ".restart-set.json"
POD = "pod"                      # the pod and every container
UNITS = {
    "web": "postal-app.service",
    "smtp": "postal-smtp-app.service",
    "worker": "postal-worker-app.service",
}
# Optional containers: started only while their flag file exists
OPTIONAL_UNITS = {
    "rspamd": ("rspamd-app.service", RSPAMD_ENV),
    "clamav": ("clamav-app.service", CLAMAV_FLAG),
}

# postal.yml section -> Postal processes reading it
RESTART_MAP = {
    "postal": ["web", "smtp", "worker"],
    "web_server": ["web"],
    "worker": ["worker"],
    "main_db": ["web", "smtp", "worker"],
    "message_db": ["web", "smtp", "worker"],
    "logging": ["web", "smtp", "worker"],
    "gelf": ["web", "smtp", "worker"],
    "smtp_server": ["smtp"],
    "dns": ["web", "smtp", "worker"],
    "smtp": ["web", "worker"],          # e-mails of Postal itself
    "rails": ["web", "smtp", "worker"],
    "rspamd": ["worker"],               # the worker inspects the messages
    "spamd": ["worker"],
    "clamav": ["worker"],
    "smtp_client": ["worker"],
    "migration_waiter": ["web", "smtp", "worker"],
    "oidc": ["web"],
}
# postal.env variable -> Postal processes reading it
ENV_RESTART_MAP = {
    "OIDC_SECRET": ["web"],
    "SMTP_PASSWORD": ["web", "worker"],
    "RSPAMD_PASSWORD": ["worker"],
}


def _digest(value):
    import hashlib
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


# Other rendered values -> containers
EXTRA_RESTART_MAP = {
    "worker_env": ["worker"],
    "rspamd": ["rspamd", "worker"],
    "clamav": ["clamav", "worker"],
    "pod_publish": [POD],              # ports published by the pod
    "worker_network": ["worker"],
}


def changed_containers(conf, env, extra=None):
    """Containers reading a section of conf, a variable of env or a value
    of extra that differs from the previous rendering"""
    extra = extra or {}
    try:
        with open(RENDERED_STATE) as fp:
            previous = json.load(fp)
    except (FileNotFoundError, ValueError):
        previous = None
    current = {
        "conf": {section: _digest(values) for section, values in conf.items()},
        "env": {key: _digest(value) for key, value in env.items()},
        "extra": {key: _digest(value) for key, value in extra.items()},
    }
    write_file(RENDERED_STATE, json.dumps(current, indent=1, sort_keys=True) + "\n", 0o600)
    if previous is None:
        return {"web", "smtp", "worker"}
    affected = set()
    for section in set(current["conf"]) | set(previous.get("conf", {})):
        if current["conf"].get(section) != previous.get("conf", {}).get(section):
            affected.update(RESTART_MAP.get(section, ["web", "smtp", "worker"]))
    for key in set(current["env"]) | set(previous.get("env", {})):
        if current["env"].get(key) != previous.get("env", {}).get(key):
            affected.update(ENV_RESTART_MAP.get(key, ["web", "smtp", "worker"]))
    for key in current["extra"]:
        if key in previous.get("extra", {}) and current["extra"][key] != previous["extra"][key]:
            affected.update(EXTRA_RESTART_MAP[key])
    return affected


def mark_restart(names):
    """Add names (keys of UNITS, or POD) to the restart set that
    configure-module applies in 80start_services"""
    names = set(names)
    if not names:
        return
    try:
        with open(RESTART_SET) as fp:
            names.update(json.load(fp))
    except (FileNotFoundError, ValueError):
        pass
    write_file(RESTART_SET, json.dumps(sorted(names)) + "\n", 0o644)


def take_restart_set():
    try:
        with open(RESTART_SET) as fp:
            names = set(json.load(fp))
    except (FileNotFoundError, ValueError):
        names = set()
    try:
        os.unlink(RESTART_SET)
    except FileNotFoundError:
        pass
    return names


def port_in_use(port):
    try:
        return agent.tcp_port_in_use(int(port))
    except OSError:
        return False  # e.g. no IPv6 on the node


# --------------------------------------------------------------------------
# configure-module
# --------------------------------------------------------------------------

def merge_request(data):
    """(current, merged settings, secret updates) of a configure-module
    request: fields left out keep their current value"""
    current = coerce(load_settings())
    merged = copy.deepcopy(current)
    merged.update({k: copy.deepcopy(v) for k, v in data.items() if k in DEFAULTS and v is not None})
    coerce(merged)
    updates = {}
    for field, var in SECRET_FIELDS.items():
        value = data.get(field)
        if isinstance(value, str) and value != "":
            updates[var] = value
    return current, merged, updates


def is_ip_address(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def is_host(value):
    return bool(value) and (is_ip_address(value) or bool(HOSTNAME_RE.match(value.lower())))


def is_https_url(value):
    from urllib.parse import urlparse
    try:
        url = urlparse(value or "")
    except ValueError:
        return False
    return url.scheme == "https" and bool(url.hostname)


def validate(data, current, settings, updates):
    """List of validation errors [{field, parameter, value, error}]"""
    errors = []

    def error(field, value, code):
        errors.append({'field': field, 'parameter': field, 'value': value, 'error': code})

    # Integers
    ranges = {
        "smtp_port": (1, 65535),
        "max_message_size": (1, 1024),
        "default_maximum_delivery_attempts": (1, 100),
        "default_maximum_hold_expiry_days": (1, 365),
        "default_suppression_list_automatic_removal_days": (1, 3650),
        "default_spam_threshold": (1, 1000),
        "default_spam_failure_threshold": (1, 1000),
        "queued_message_lock_stale_days": (1, 365),
        "smtp_client_open_timeout": (1, 600),
        "smtp_client_read_timeout": (1, 600),
        "app_smtp_port": (1, 65535),
        "rspamd_port": (1, 65535),
        "spamd_port": (1, 65535),
        "clamav_port": (1, 65535),
        "web_server_max_threads": (1, 64),
        "worker_threads": (1, 64),
        "main_db_pool_size": (1, 256),
        "gelf_port": (1, 65535),
    }
    for key, (low, high) in ranges.items():
        value = settings[key]
        if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
            error(key, value, "invalid_number")
    for key in BOOL_FIELDS:
        if not isinstance(settings[key], bool):
            error(key, settings[key], "invalid_boolean")
    for key in LIST_FIELDS:
        if not isinstance(settings[key], list):
            error(key, settings[key], "invalid_list")
    if errors:
        return errors

    # Web interface
    host = settings["host"]
    if not HOSTNAME_RE.match(host or ""):
        error("host", host, "host_format")
    elif host != (os.environ.get("TRAEFIK_HOST") or "").lower() and agent.http_route_in_use(domain=host):
        error("host", host, "domain_already_used_in_traefik")

    # SMTP server
    if settings["smtp_hostname"] and not HOSTNAME_RE.match(settings["smtp_hostname"]):
        error("smtp_hostname", settings["smtp_hostname"], "host_format")
    port = settings["smtp_port"]
    if port < 23:
        error("smtp_port", port, "port_privileged")
    elif port == int(os.environ.get("TCP_PORT") or 0):
        error("smtp_port", port, "port_reserved")
    else:
        try:
            taken = ports_taken_on_node()
        except Exception as ex:
            log(agent.SD_WARNING + f"Cannot list the mail modules of the node: {ex}")
            taken = {}
        active = subprocess.run(['systemctl', '--user', '-q', 'is-active', 'postal.service']).returncode == 0
        if port in taken:
            error("smtp_port", f"{taken[port]}:{port}", "mail_module_on_node")
        elif not (active and port == current["smtp_port"]) and port_in_use(port):
            error("smtp_port", port, "port_in_use")

    # Delivery
    if settings["default_spam_failure_threshold"] < settings["default_spam_threshold"]:
        error("default_spam_failure_threshold", settings["default_spam_failure_threshold"], "below_spam_threshold")
    if settings["helo_hostname"] and not HOSTNAME_RE.match(settings["helo_hostname"]):
        error("helo_hostname", settings["helo_hostname"], "host_format")

    # Relays
    if len(settings["smtp_relays"]) > 10:
        error("smtp_relays", len(settings["smtp_relays"]), "too_many_relays")
    for relay in settings["smtp_relays"]:
        if not is_host(relay["host"]):
            error("smtp_relays", relay["host"], "invalid_host")
        elif not 1 <= relay["port"] <= 65535:
            error("smtp_relays", relay["port"], "invalid_number")
        elif relay["ssl_mode"] not in RELAY_SSL_MODES:
            error("smtp_relays", relay["ssl_mode"], "invalid_ssl_mode")
    if settings["relay_via_cluster_smarthost"]:
        sh = smarthost()
        if not sh["enabled"] or not sh["host"]:
            error("relay_via_cluster_smarthost", True, "cluster_smarthost_disabled")
        elif sh["username"]:
            error("relay_via_cluster_smarthost", True, "cluster_smarthost_requires_auth")
    if settings["cluster_relay_provider"] and settings["smtp_port"] != 25:
        error("cluster_relay_provider", True, "provider_requires_port_25")

    # E-mails of Postal itself
    if settings["app_smtp_mode"] not in APP_SMTP_MODES:
        error("app_smtp_mode", settings["app_smtp_mode"], "invalid_choice")
    elif settings["app_smtp_mode"] == "custom":
        if not is_host(settings["app_smtp_host"]):
            error("app_smtp_host", settings["app_smtp_host"], "invalid_host")
        if settings["app_smtp_tls"] not in APP_SMTP_TLS:
            error("app_smtp_tls", settings["app_smtp_tls"], "invalid_choice")
        if settings["app_smtp_username"] and not (updates.get("SMTP_PASSWORD") or read_secrets().get("SMTP_PASSWORD")):
            error("app_smtp_password", "", "password_required")
    if settings["from_address"] and not EMAIL_RE.match(settings["from_address"]):
        error("from_address", settings["from_address"], "invalid_email")

    # OpenID Connect
    if settings["oidc_enabled"]:
        if not is_https_url(settings["oidc_issuer"]):
            error("oidc_issuer", settings["oidc_issuer"], "invalid_https_url")
        if not settings["oidc_identifier"]:
            error("oidc_identifier", "", "required")
        if not (updates.get("OIDC_SECRET") or read_secrets().get("OIDC_SECRET")):
            error("oidc_secret", "", "required")
        if "openid" not in settings["oidc_scopes"]:
            error("oidc_scopes", ",".join(settings["oidc_scopes"]), "openid_scope_required")
        for scope in settings["oidc_scopes"]:
            if not SCOPE_RE.match(scope):
                error("oidc_scopes", scope, "invalid_scope")
        for key in ("oidc_uid_field", "oidc_email_address_field", "oidc_name_field"):
            if not FIELD_RE.match(settings[key] or ""):
                error(key, settings[key], "invalid_field")
        if not settings["oidc_discovery"]:
            for key in ("oidc_authorization_endpoint", "oidc_token_endpoint", "oidc_userinfo_endpoint", "oidc_jwks_uri"):
                if not is_https_url(settings[key]):
                    error(key, settings[key], "invalid_https_url")
    if not settings["oidc_local_authentication_enabled"] and not settings["oidc_enabled"]:
        # Without local logins and without OIDC nobody could log in
        error("oidc_local_authentication_enabled", False, "local_authentication_required")

    # Message inspection
    for name in ("rspamd", "spamd", "clamav"):
        if settings[f"{name}_enabled"] and not is_host(settings[f"{name}_host"]):
            error(f"{name}_host", settings[f"{name}_host"], "invalid_host")

    # DNS names
    for key in ("dns_spf_include", "dns_return_path_domain", "dns_route_domain", "dns_track_domain"):
        if settings[key] and not HOSTNAME_RE.match(settings[key]):
            error(key, settings[key], "host_format")
    for name in settings["dns_mx_records"]:
        if not HOSTNAME_RE.match(name):
            error("dns_mx_records", name, "host_format")
    for key in ("dns_dkim_identifier", "dns_custom_return_path_prefix", "dns_domain_verify_prefix"):
        if not re.match(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$", settings[key] or ""):
            error(key, settings[key], "invalid_label")

    # Optional containers and the worker network
    if needs_extra_ports(settings) and not extra_ports() and not hasattr(agent, "allocate_ports"):
        error("rspamd_container" if settings["rspamd_container"] else "clamav_container", True,
              "ports_unavailable")
    if settings["rspamd_webui"] and not settings["rspamd_container"]:
        error("rspamd_webui", True, "rspamd_container_required")
    if settings["rspamd_container"] and settings["rspamd_enabled"]:
        # One rspamd: the container replaces an external one
        error("rspamd_enabled", True, "rspamd_container_and_external")
    if settings["clamav_container"] and settings["clamav_enabled"]:
        error("clamav_enabled", True, "clamav_container_and_external")

    # Processes
    if settings["main_db_pool_size"] < max(settings["web_server_max_threads"], settings["worker_threads"]):
        error("main_db_pool_size", settings["main_db_pool_size"], "pool_below_threads")

    # Logging and advanced
    if settings["gelf_host"] and not is_host(settings["gelf_host"]):
        error("gelf_host", settings["gelf_host"], "invalid_host")
    for net in settings["trusted_proxies"]:
        try:
            ipaddress.ip_network(net, strict=False)
        except ValueError:
            error("trusted_proxies", net, "invalid_network")
    for dest in settings["allowed_request_destinations"]:
        try:
            ipaddress.ip_network(dest, strict=False)
        except ValueError:
            if not HOSTNAME_RE.match(dest.lower()):
                error("allowed_request_destinations", dest, "invalid_destination")

    # Free text written in postal.yml or postal.env
    for key in ("from_name", "oidc_name", "app_smtp_username", "rspamd_flags", "oidc_identifier"):
        if any(c in str(settings[key]) for c in "\r\n\0"):
            error(key, "", "invalid_characters")
    for field, var in SECRET_FIELDS.items():
        if var in updates and any(c in updates[var] for c in "\r\n\0"):
            error(field, "", "invalid_characters")
    return errors


# --------------------------------------------------------------------------
# TLS certificate of the SMTP server
# --------------------------------------------------------------------------

def fetch_certificate(name):
    """Copy the Traefik certificate of name to tls/ (0600 key); without one
    and without files, write a self-signed certificate. Returns True if the
    files changed."""
    import base64
    import agent.tasks
    os.makedirs(TLS_DIR, mode=0o700, exist_ok=True)
    cert = key = None
    try:
        response = agent.tasks.run(
            agent_id=agent.resolve_agent_id("traefik@node"),
            action='get-certificate',
            data={'fqdn': name},
            extra={'isNotificationHidden': True},
        )
        if response['exit_code'] == 0 and response['output'].get('certificates'):
            item = response['output']['certificates'][0]
            cert = base64.b64decode(item['cert']).decode()
            key = base64.b64decode(item['key']).decode()
    except Exception as ex:
        log(agent.SD_WARNING + f"Cannot get the certificate of {name} from Traefik: {ex}")
    if cert and key:
        changed = write_file(TLS_CERT, cert, 0o644)
        return write_file(TLS_KEY, key, 0o600) or changed
    if os.path.exists(TLS_CERT) and os.path.exists(TLS_KEY):
        return False
    log(f"No Traefik certificate for {name} yet: using a self-signed one")
    old = os.umask(0o077)
    try:
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "3650",
                        "-subj", f"/CN={name}", "-addext", f"subjectAltName=DNS:{name}",
                        "-keyout", TLS_KEY, "-out", TLS_CERT],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        os.umask(old)
    os.chmod(TLS_KEY, 0o600)
    os.chmod(TLS_CERT, 0o644)
    return True


# --------------------------------------------------------------------------
# Track domains
# --------------------------------------------------------------------------

def track_domain_status(settings):
    """[{name, status}] of the track domain routes (bin/postal-track-routes),
    with the state of their Let's Encrypt certificate as Traefik reports it"""
    import agent.tasks
    try:
        with open(TRACK_ROUTES_STATE) as fp:
            state = json.load(fp)
    except (FileNotFoundError, ValueError):
        state = {}
    pending = set()
    prefix = os.environ.get("MODULE_ID", "") + "-track-"
    if state.get("routes") and settings["lets_encrypt"]:
        try:
            response = agent.tasks.run(agent_id=agent.resolve_agent_id("traefik@node"), action="list-routes",
                                       data={"expand_list": True}, extra={"isNotificationHidden": True})
            for route in response.get("output") or []:
                if isinstance(route, dict) and route.get("instance", "").startswith(prefix) \
                        and route.get("lets_encrypt_status") == "pending":
                    pending.add(route["instance"].removeprefix(prefix))
        except Exception as ex:
            log(agent.SD_WARNING + f"list-routes failed: {ex}")
    names = []
    for name, conf in sorted(state.get("routes", {}).items()):
        if not conf.get("lets_encrypt"):
            status = "no_lets_encrypt"
        elif name in pending:
            status = "pending"  # no certificate yet: check the DNS record of the name
        else:
            status = "obtained"
        names.append({"name": name, "status": status})
    for name in state.get("skipped", []):
        names.append({"name": name, "status": "used_by_another_route"})
    return names


def smtp_port_choices():
    """[{port, used_by}] of the usual SMTP ports: used_by is the mail
    module of the node holding it, or empty"""
    try:
        taken = ports_taken_on_node()
    except Exception as ex:
        log(agent.SD_WARNING + f"Cannot list the mail modules of the node: {ex}")
        taken = {}
    return [{"port": port, "used_by": taken.get(port, "")} for port in (2525, 25, 587)]


# --------------------------------------------------------------------------
# Optional containers and the host-network worker
# --------------------------------------------------------------------------

def rspamd_password():
    """The rspamd controller password, generated when rspamd is enabled
    (state/rspamd.env, 0600, like ns8-mail); "" while it is off"""
    return read_env(RSPAMD_ENV).get("RSPAMD_adminpw", "")


def rspamd_state(settings):
    return {"container": settings["rspamd_container"], "controller": RSPAMD_CONTROLLER}


RSPAMD_CONTROLLER = """# Generated by configure-module of ns8-postal: do not edit, changes are lost.
# Mounted over override.d/worker-controller.inc of the rspamd container.
# The controller listens on the pod network; the pod publishes it only on
# 127.0.0.1 of the node (second TCP port of the module), for the route of the web
# interface (Traefik injects the password for the users the NS8 api-server
# authorizes) and for the Postal worker of the host network. No address is
# trusted: every request needs the password.
count = 1;
bind_socket = "*:11334";
password = "{= env.adminpw =}";
enable_password = "{= env.adminpw =}";
secure_ip = [];
static_dir = "${WWWDIR}";
"""


def render_rspamd(settings):
    if not settings["rspamd_container"]:
        # rspamd.env is the ConditionPathExists of rspamd-app.service
        try:
            os.unlink(RSPAMD_ENV)
        except FileNotFoundError:
            pass
        return
    if not rspamd_password():
        write_env(RSPAMD_ENV, {"RSPAMD_adminpw": secrets.token_urlsafe(24)})
    os.makedirs(RSPAMD_DIR, exist_ok=True)
    write_file(RSPAMD_CONTROLLER_FILE, RSPAMD_CONTROLLER, 0o644)


def rspamd_route_status():
    """{"status": "published"|"off"|"conflict", "owner": route instance}"""
    try:
        with open(RSPAMD_ROUTE_STATE) as fp:
            return json.load(fp)
    except (FileNotFoundError, ValueError):
        return {"status": "off", "owner": ""}


def render_clamav(settings):
    if settings["clamav_container"]:
        write_file(CLAMAV_FLAG, "1\n", 0o644)
    else:
        try:
            os.unlink(CLAMAV_FLAG)
        except FileNotFoundError:
            pass


def extra_ports():
    """(rspamd controller port, clamd port) of the node, or None"""
    ports = [int(p) for p in os.environ.get("TCP_PORTS", "").split(",") if p.strip().isdigit()]
    if len(ports) >= 3:
        return ports[1], ports[2]
    ports = [int(p) for p in os.environ.get("POSTAL_EXTRA_TCP_PORTS", "").split(",") if p.strip().isdigit()]
    if len(ports) == 2:
        return ports[0], ports[1]
    return None


def needs_extra_ports(settings):
    return settings["rspamd_container"] or settings["clamav_container"]


def ensure_extra_ports():
    """Allocate the two ports of the optional containers for an install
    created with one TCP port (older releases). Returns the ports."""
    found = extra_ports()
    if found:
        return found
    start, end = agent.allocate_ports(2, "tcp", keep_existing=True)
    agent.set_env("POSTAL_EXTRA_TCP_PORTS", f"{start},{start + 1}")
    os.environ["POSTAL_EXTRA_TCP_PORTS"] = f"{start},{start + 1}"
    log(f"Allocated the TCP ports {start} and {start + 1} for rspamd and ClamAV")
    return start, start + 1


def rspamd_url():
    ports = extra_ports()
    return f"http://127.0.0.1:{ports[0]}" if ports else ""


def pod_publish(settings):
    """Extra --publish options of the pod (POSTAL_POD_PUBLISH)"""
    ports = extra_ports()
    args = []
    if ports and settings["rspamd_container"]:
        args.append(f"--publish=127.0.0.1:{ports[0]}:11334")
    if ports and settings["clamav_container"] and settings["worker_host_network"]:
        args.append(f"--publish=127.0.0.1:{ports[1]}:3310")
    return " ".join(args)


def worker_network_args(settings):
    """podman run options of the worker network (POSTAL_WORKER_NETWORK_ARGS)"""
    if settings["worker_host_network"]:
        # MariaDB through its unix socket, shared by the mysqld-run volume:
        # no TCP port of the database is published
        return "--network=host --volume=mysqld-run:/run/mysqld:z"
    return "--pod=postal"


def render_worker_env(settings):
    """Variables of the worker only (postal-worker.env, 0600): with the
    host network, the addresses of the pod services seen from the node"""
    if not settings["worker_host_network"]:
        return {}
    env = {
        "MAIN_DB_HOST": "localhost",       # unix socket /run/mysqld/mysqld.sock
        "MESSAGE_DB_HOST": "localhost",
        "HEALTH_SERVER_BIND_ADDRESS": WORKER_HEALTH_LOOPBACK,
        "HEALTH_SERVER_PORT": os.environ.get("TCP_PORT", "9090"),
    }
    ports = extra_ports()
    if settings["rspamd_container"] and ports:
        env.update({
            "RSPAMD_HOST": "127.0.0.1",
            "RSPAMD_PORT": str(ports[0]),
            "RSPAMD_PASSWORD": rspamd_password(),
        })
    if settings["clamav_container"] and ports:
        env.update({"CLAMAV_HOST": "127.0.0.1", "CLAMAV_PORT": str(ports[1])})
    return env


def worker_health_url():
    if os.environ.get("POSTAL_WORKER_NETWORK_ARGS", "").startswith("--network=host"):
        return f"http://{WORKER_HEALTH_LOOPBACK}:{os.environ.get('TCP_PORT', '9090')}/health"
    return "http://127.0.0.1:9090/health"


def set_unit_env(settings):
    """Non-secret variables the units read (state/environment)"""
    agent.set_env("POSTAL_POD_PUBLISH", pod_publish(settings))
    agent.set_env("POSTAL_WORKER_NETWORK_ARGS", worker_network_args(settings))


def rspamd_path_route_owner(host):
    """Instance of another Traefik route serving <host>/rspamd, or "".
    agent.http_route_in_use() cannot tell: the route of the Postal host
    name itself answers on every path."""
    import agent.tasks
    try:
        response = agent.tasks.run(agent_id=agent.resolve_agent_id("traefik@node"), action="list-routes",
                                   data={"expand_list": True}, extra={"isNotificationHidden": True})
    except Exception as ex:
        log(agent.SD_WARNING + f"list-routes failed: {ex}")
        return ""
    ours = os.environ.get("MODULE_ID", "") + "-rspamd"
    for route in response.get("output") or []:
        if not isinstance(route, dict) or route.get("instance") == ours:
            continue
        if (route.get("host") or "").lower() == host and (route.get("path") or "").rstrip("/") == RSPAMD_PATH:
            return route.get("instance", "")
    return ""
