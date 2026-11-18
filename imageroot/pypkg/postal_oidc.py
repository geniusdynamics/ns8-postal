#
# Copyright (C) 2026 Genius Dynamics
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""Apply Postal's choice of NS8 OIDC provider through the NS8 client API."""

import json
import os
import sys

import agent
import agent.tasks
from agent.ldapproxy import Ldapproxy
import postal_ns8 as postal


class RegistrationError(Exception):
    def __init__(self, field, code):
        self.field = field
        self.code = code
        super().__init__(code)

    def report(self):
        agent.set_status("validation-failed")
        json.dump([{
            "field": self.field, "parameter": self.field, "value": "", "error": self.code,
        }], sys.stdout)
        raise SystemExit(3)


def active_domain(settings):
    if settings["oidc_enabled"] and settings["oidc_provider"]:
        return settings["oidc_domain"]
    return ""


def resolve_provider(rdb, settings):
    selection = postal.managed_oidc_providers(rdb).get(settings["oidc_provider"])
    if not selection:
        raise RegistrationError("oidc_provider", "oidc_provider_unavailable")
    domain = settings["oidc_domain"]
    if selection["domain"] and domain != selection["domain"]:
        raise RegistrationError("oidc_domain", "oidc_domain_not_served")
    if domain not in Ldapproxy().get_domains_list():
        raise RegistrationError("oidc_domain", "oidc_domain_unavailable")
    return selection


def bind_domains(domains):
    if not agent.bind_user_domains(domains):
        raise RegistrationError("oidc_domain", "oidc_registration_failed")


def apply(current, settings, updates):
    """Register before changing local credentials and reconcile the domain binding."""
    old_domain = active_domain(current)
    new_domain = active_domain(settings)
    if not new_domain:
        if old_domain:
            bound = agent.get_bound_domain_list(agent.redis_connect())
            if old_domain in bound:
                bind_domains([domain for domain in bound if domain != old_domain])
        if not settings["oidc_provider"]:
            settings["oidc_domain"] = ""
        return

    updates.pop("OIDC_SECRET", None)
    same_provider = current["oidc_provider"] == settings["oidc_provider"] and old_domain == new_domain
    module_id = os.environ["MODULE_ID"]
    if (
        same_provider and current["host"] == settings["host"]
        and current["oidc_identifier"] == module_id and postal.read_secrets().get("OIDC_SECRET")
    ):
        for field, value in current.items():
            if field.startswith("oidc_") and field != "oidc_local_authentication_enabled":
                settings[field] = value
        return

    rdb = agent.redis_connect()
    provider = resolve_provider(rdb, settings)
    issuer = provider["issuer"] + new_domain
    if same_provider and current["oidc_issuer"] and issuer != current["oidc_issuer"]:
        raise RegistrationError("oidc_provider", "oidc_issuer_changed")
    bound = agent.get_bound_domain_list(rdb)
    added_domain = new_domain not in bound
    if added_domain:
        bind_domains([*bound, new_domain])
    try:
        try:
            result = agent.tasks.run(
                f"module/{provider['module_id']}", "register-client",
                data={
                    "domain": new_domain,
                    "redirect_uris": [postal.oidc_redirect_uri(settings)],
                    "post_logout_redirect_uris": [],
                },
                extra={"isNotificationHidden": True},
            )
        except Exception as error:
            raise RegistrationError("oidc_provider", "oidc_registration_failed") from error
        response = result.get("output")
        if result.get("exit_code") != 0 or not isinstance(response, dict):
            raise RegistrationError("oidc_provider", "oidc_registration_failed")
        if response.get("issuer") != issuer:
            raise RegistrationError("oidc_provider", "oidc_issuer_changed")
        secret = response.get("client_secret")
        if (
            response.get("client_id") != module_id or response.get("realm") != new_domain
            or not isinstance(secret, str) or not secret or any(c in secret for c in "\r\n\0")
        ):
            raise RegistrationError("oidc_provider", "oidc_registration_failed")
        if old_domain and old_domain != new_domain and old_domain in bound:
            bind_domains([domain for domain in bound if domain != old_domain and domain != new_domain] + [new_domain])
    except RegistrationError:
        if added_domain:
            agent.bind_user_domains(bound)
        raise

    settings.update({
        "oidc_name": provider["name"],
        "oidc_issuer": issuer,
        "oidc_identifier": module_id,
        "oidc_discovery": True,
        "oidc_scopes": ["openid", "email", "profile"],
        "oidc_uid_field": "sub",
        "oidc_email_address_field": "email",
        "oidc_name_field": "name",
        "oidc_authorization_endpoint": "",
        "oidc_token_endpoint": "",
        "oidc_userinfo_endpoint": "",
        "oidc_jwks_uri": "",
    })
    updates["OIDC_SECRET"] = secret
