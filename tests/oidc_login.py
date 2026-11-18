#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Follow Postal's real OAuth callback on an isolated NS8 test node."""

from html.parser import HTMLParser
from http.client import HTTPSConnection
from http.cookies import SimpleCookie
import ssl
import sys
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit


class Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = {}
        self.csrf = ""
        self.keycloak_login = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type") == "hidden" and attrs.get("name"):
            self.hidden[attrs["name"]] = attrs.get("value", "")
        if tag == "meta" and attrs.get("name") == "csrf-token":
            self.csrf = attrs.get("content", "")
        if tag == "form" and attrs.get("id") == "kc-form-login":
            self.keycloak_login = attrs.get("action", "")


def login(postal, provider, kind, username, password):
    cookies = {}
    context = ssl._create_unverified_context()  # Postal itself verifies the provider with the fixture CA.

    def call(url, form=None):
        target = urlsplit(url)
        assert target.scheme == "https" and target.netloc in (postal, provider)
        jar = cookies.setdefault(target.netloc, SimpleCookie())
        headers = {
            "Host": target.netloc,
            "Cookie": "; ".join(f"{key}={item.coded_value}" for key, item in jar.items()),
        }
        if form is not None:
            headers.update({
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": f"https://{target.netloc}",
            })
        conn = HTTPSConnection("127.0.0.1", context=context, timeout=15)
        try:
            path = urlunsplit(("", "", target.path or "/", target.query, ""))
            conn.request("GET" if form is None else "POST", path, None if form is None else urlencode(form), headers)
            response = conn.getresponse()
            for value in response.headers.get_all("Set-Cookie", []):
                jar.load(value)
            parsed = Form()
            parsed.feed(response.read().decode(errors="replace"))
            location = response.headers.get("Location")
            return response.status, urljoin(url, location) if location else "", parsed
        finally:
            conn.close()

    if kind == "lemonldapng":
        portal = f"https://{provider}/"
        status, _, page = call(portal)
        assert status == 200 and page.hidden.get("token"), "LemonLDAP::NG login form"
        status, _, _ = call(portal, {**page.hidden, "user": username, "password": password})
        assert "lemonldap" in cookies[provider], f"LemonLDAP::NG login HTTP {status}"

    status, _, page = call(f"https://{postal}/login")
    assert status == 200 and page.csrf, "Postal login form"
    status, location, _ = call(f"https://{postal}/auth/oidc", {"authenticity_token": page.csrf})
    assert status in (302, 303) and urlsplit(location).netloc == provider, f"Postal OIDC start HTTP {status} to {urlsplit(location).netloc}{urlsplit(location).path}"

    if kind == "lemonldapng":
        status, location, _ = call(location + "&confirm=1")
    else:
        status, location, page = call(location)
        for _ in range(4):
            if status not in (302, 303):
                break
            status, location, page = call(location)
        assert status == 200 and page.keycloak_login, "Keycloak login form"
        status, location, _ = call(
            page.keycloak_login, {"username": username, "password": password},
        )

    callback = urlsplit(location)
    assert status in (302, 303) and callback.netloc == postal and callback.path == "/auth/oidc/callback", f"Provider authorization HTTP {status}"
    status, location, _ = call(location)
    assert status in (302, 303) and urlsplit(location).netloc == postal and urlsplit(location).path != "/login", f"Postal callback HTTP {status} to {urlsplit(location).path}"
    status, location, _ = call(location)
    assert status == 200 or (status in (302, 303) and urlsplit(location).path != "/login"), f"Postal session HTTP {status}"


if __name__ == "__main__":
    login(*sys.argv[1:])
