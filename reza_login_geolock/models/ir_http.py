from odoo import models
from odoo.exceptions import AccessDenied
from odoo.http import SessionExpiredException, request

from .res_users import PARAM_COUNTRIES, PARAM_MODE

SESSION_KEY = "reza_geolock_ok"


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
        params = request.env["ir.config_parameter"].sudo()
        stamp = "%s|%s|%s" % (request.httprequest.remote_addr,
                              params.get_param(PARAM_MODE, "report"),
                              params.get_param(PARAM_COUNTRIES) or "AU")
        if session.get(SESSION_KEY) == stamp:
            return
        try:
            request.env["res.users"].sudo().browse(uid)._reza_geolock_check("session")
        except AccessDenied:
            session.logout(keep_db=True)
            # Odoo saves the session only after a successful dispatch, so the
            # logout would not stick through the exception below. Save it now.
            request._save_session()
            raise SessionExpiredException("Staff session ended: sign-in is not allowed from this country.")
        session[SESSION_KEY] = stamp
