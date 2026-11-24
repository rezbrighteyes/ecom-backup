import logging

from odoo import models
from odoo.exceptions import AccessDenied
from odoo.http import request
from odoo.http.session import SessionExpiredException, logout, save_session

from .geolock_ip import PARAM_IPS_STAMP
from .res_users import PARAM_COUNTRIES, PARAM_MODE

SESSION_KEY = "reza_geolock_ok"

_logger = logging.getLogger(__name__)


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _authenticate(cls, endpoint):
        super()._authenticate(endpoint)
        cls._reza_geolock_session()

    @classmethod
    def _reza_geolock_session(cls):
        """Geolock an OPEN staff session, not only the login.

        A session cookie works from anywhere, so someone already signed in who
        travels, or an attacker holding a stolen cookie, would otherwise keep
        working. The verdict is remembered in the session per address and
        setting, so the GeoIP lookup runs once per change of address, not on
        every request. In Block mode the session is ended and the browser is
        sent back to the login page, where the login itself is refused."""
        session = request.session
        uid = session.uid
        if not uid:
            return
        try:
            params = request.env["ir.config_parameter"].sudo()
            stamp = "%s|%s|%s|%s" % (request.httprequest.remote_addr,
                                     params.get_str(PARAM_MODE, "report"),
                                     params.get_str(PARAM_COUNTRIES) or "AU",
                                     params.get_str(PARAM_IPS_STAMP) or "")
        except Exception:                                    # noqa: BLE001
            # Never lock staff out on our own fault: a broken stamp lets the
            # request through and is logged.
            _logger.exception("Staff sign-in geolock: session check failed, request allowed")
            return
        if session.get(SESSION_KEY) == stamp:
            return
        try:
            request.env["res.users"].sudo().browse(uid)._reza_geolock_check("session")
        except AccessDenied:
            logout(session, keep_db=True)
            # Odoo saves the session only after a successful dispatch, so the
            # logout would not stick through the exception below. Save it now.
            save_session(request)
            raise SessionExpiredException("Staff session ended: sign-in is not allowed from this country.")
        session[SESSION_KEY] = stamp
