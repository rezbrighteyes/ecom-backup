# -*- coding: utf-8 -*-
"""HTTP boundary of the catalogue export.

One route covers the whole /storefront prefix, for every method, with
auth='none' and website=False, so every request under the prefix reaches this
module's pre-dispatch check (gate.py) before Odoo parses it:

* auth='none': no session user is attached, so no website page, login
  redirect or session pricelist/cart is involved. The website comes from the
  Host and the work runs as that website's public user.
* website=False / multilang=False: no frontend pre-dispatch (language
  redirects, website error pages, debug tracebacks) runs for this prefix.
* catch-all, all methods: an unknown path, a POST or a trailing slash gets the
  SAME minimal 404 as a missing token. Nothing distinguishes the real
  endpoints from a missing one without the token.

Every refusal is the same JSON 404 with Cache-Control: no-store. A failure
after authentication is a JSON 500 with no traceback (logged server-side).
"""

import logging

from odoo import http
from odoo.http import request

from .. import catalogue, gate
from ..models.ir_http import ROUTING_FLAG

_logger = logging.getLogger(__name__)


class StorefrontCatalogue(http.Controller):

    @http.route(["/storefront", "/storefront/<path:subpath>"], type="http", auth="none",
                csrf=False, save_session=False, sitemap=False, website=False,
                multilang=False, **{ROUTING_FLAG: True})
    def storefront(self, **kwargs):
        authorised = False
        try:
            # Granted by the pre-dispatch check, and checked again here: the
            # operation comes from the request path, never from a parameter.
            granted = getattr(request, "reza_storefront_granted", None) and gate.check(request)
            if not granted:
                return gate.refusal(request)
            endpoint, website = granted
            site = catalogue.public_site(website)
            authorised = True

            gate.neutralise_request(request)
            pricing = catalogue.anonymous_pricing(site)
            catalogue.apply_pricing(request, site, pricing)
            if endpoint == "meta":
                return gate.json_response(request, catalogue.meta(site), 200)
            hreq = request.httprequest
            paging = catalogue.parse_paging(hreq.args.get("page"), hreq.args.get("limit"))
            if paging is None:
                return gate.json_response(request, {"error": "bad_paging"}, 400)
            return gate.json_response(
                request, catalogue.products_page(site, paging[0], paging[1], pricing), 200)
        except catalogue.PageTooLarge as exc:
            request.env.cr.rollback()
            return gate.json_response(request, {
                "error": "too_large", "what": exc.what, "max": exc.bound}, 400)
        except Exception:  # noqa: BLE001 - never a framework error page here
            request.env.cr.rollback()
            if not authorised:
                return gate.refusal(request)
            _logger.exception("storefront catalogue export failed")
            return gate.json_response(request, {"error": "internal"}, 500)
