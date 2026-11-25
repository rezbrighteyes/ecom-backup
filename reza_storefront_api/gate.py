# -*- coding: utf-8 -*-
"""Request checks for the storefront API, run BEFORE Odoo parses the request.

ir.http._pre_dispatch (models/ir_http.py) calls check() for this API's route
ahead of every other pre-dispatch hook, and before the HTTP dispatcher reads
form fields, files or binds parameters. A refused request therefore never
reaches body parsing, parameter binding, website hooks (geolock, theme gates)
or Odoo's error pages: it gets refusal() and nothing else.

check() answers (endpoint, website) or None. Everything is refused the same
way: wrong method, a path other than the two endpoints as the client sent
them (no language prefix, rewrite or reroute), a body, an unknown or repeated
query parameter, a session cookie, a bad token, a missing or invalid
Cloudflare Access JWT (when access.py is configured), an unknown Host, a
website whose user is not public, a closed or prelaunch shop.
"""

import json
from urllib.parse import urlsplit

from odoo import SUPERUSER_ID

from . import access, catalogue

TOKEN_HEADER = "X-Storefront-Token"
ENDPOINTS = {
    "/storefront/v1/catalogue": ("products", frozenset({"page", "limit"})),
    "/storefront/v1/catalogue/meta": ("meta", frozenset()),
    "/storefront/v1/content": ("content", frozenset()),
}
NOT_FOUND = {"error": "not_found"}


def json_response(request, payload, status):
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return request.make_response(body, status=status, headers=[
        ("Content-Type", "application/json; charset=utf-8"),
        ("Cache-Control", "no-store"),
    ])


def refusal(request):
    return json_response(request, NOT_FOUND, 404)


def _original_path(hreq):
    # REQUEST_URI is what the client sent; Odoo's reroute() (language prefix,
    # website rewrite) leaves it unchanged and rewrites PATH_INFO only.
    raw = hreq.environ.get("REQUEST_URI")
    return urlsplit(raw).path if raw else hreq.path


def check(request):
    hreq = request.httprequest
    if hreq.method != "GET":
        return None
    path = hreq.path
    if _original_path(hreq) != path or path not in ENDPOINTS:
        return None
    endpoint, allowed_args = ENDPOINTS[path]
    if hreq.content_length or "transfer-encoding" in hreq.headers:
        return None
    for key in hreq.args:
        if key not in allowed_args or len(hreq.args.getlist(key)) != 1:
            return None
    if "session_id" in hreq.cookies:
        return None
    env = request.env(user=SUPERUSER_ID)
    if not catalogue.token_ok(env, hreq.headers.get(TOKEN_HEADER)):
        return None
    website = catalogue.website_for_host(env, hreq.host, hreq.scheme)
    if not website:
        return None
    # Second, independent lock, checked only after the token so a caller
    # without it can never make this worker fetch Cloudflare's keys. The JWT
    # must carry the AUD configured for THIS website.
    if not access.access_ok(env, hreq.headers.get(access.JWT_HEADER), website.id):
        return None
    site = catalogue.public_site(website)
    if site is None or not catalogue.shop_open(site):
        return None
    return endpoint, website


def neutralise_request(request):
    """The export is the canonical anonymous view: no country from GeoIP.
    18/20: GeoIP("") on 20; 18 needs an address, and 0.0.0.0 has no country."""
    request.geoip = type(request.geoip)("")
