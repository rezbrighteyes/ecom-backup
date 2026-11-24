# -*- coding: utf-8 -*-
"""Answer the storefront API's refusals before Odoo touches the request.

Core runs ir.http._pre_dispatch() for every matched route before the
controller, and the HTTP dispatcher then parses form fields and files and
binds query parameters, all before the controller's own code. Failures there
(an int() on ?affiliate_id=x, a form-size limit, a parameter colliding with a
Python argument) would reach Odoo's error handling instead of this API's
minimal 404. For this API's route only, gate.check() runs FIRST, and a refusal
is returned at once through werkzeug's abort(response), which Odoo serves as
is. Any failure of the remaining pre-dispatch hooks is answered the same way.

This adds no RPC surface: ir.http is an AbstractModel and the only method is
a private (underscore) classmethod, which Odoo refuses to call over RPC.
"""

import logging
import re

import werkzeug.exceptions

from odoo import models
from odoo.http import request

from .. import gate

_logger = logging.getLogger(__name__)
ROUTING_FLAG = "reza_storefront_api"
# /<language>/storefront/...: Odoo's language routing would redirect or
# reroute it onto the API before any route hook runs. Refused in _match.
_LANG_ALIAS = re.compile(r"^/[a-z]{2,3}(?:[_-][A-Za-z0-9]{2,8})*/storefront(?:/|$)", re.IGNORECASE)


def _refuse():
    # Never save (and so never issue) a session for this API, refused or not.
    # Set first: a refusal aborts before the dispatcher applies the route's
    # save_session=False, and Odoo still saves the session after an abort.
    if getattr(request, "session", None) is not None:
        request.session.can_save = False
    werkzeug.exceptions.abort(gate.refusal(request))


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _match(cls, path):
        if _LANG_ALIAS.match(path or ""):
            _refuse()
        return super()._match(path)

    @classmethod
    def _pre_dispatch(cls, rule, args):
        if not getattr(rule.endpoint, "routing", {}).get(ROUTING_FLAG):
            return super()._pre_dispatch(rule, args)
        request.session.can_save = False
        try:
            granted = gate.check(request)
        except Exception:  # noqa: BLE001 - never a framework error page here
            _logger.exception("storefront API request check failed")
            granted = None
        if not granted:
            _refuse()
        try:
            super()._pre_dispatch(rule, args)
        except Exception:  # noqa: BLE001 - any failure becomes the API's 404
            _refuse()
        request.reza_storefront_granted = granted
        return None
