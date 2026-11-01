import contextlib
import ipaddress
import logging
import threading
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models
from odoo.exceptions import AccessDenied
from odoo.http import GeoIP, request
from odoo.modules import module as odoo_module

_logger = logging.getLogger(__name__)

PARAM_MODE = "reza_login_geolock.mode"
PARAM_COUNTRIES = "reza_login_geolock.countries"
# A blocked RPC client retries on every call; one event per user, address,
# channel and outcome per hour is enough to see it.
EVENT_QUIET = timedelta(hours=1)
# Set by controllers/rpc.py for the length of one XML-RPC / JSON-RPC call.
RPC_CLIENT_ATTR = "reza_geolock_rpc_client"


def _client():
    """(ip, user agent) of the caller, or None outside an HTTP request."""
    if request:
        return request.httprequest.remote_addr, request.httprequest.user_agent.string or ""
    return getattr(threading.current_thread(), RPC_CLIENT_ATTR, None)


def _country_of(ip):
    """ISO country code for a public address, or None.

    None means "do not judge": no address, a private or loopback address
    (Odoo.sh's own scheduled jobs call in from 10.x), or one the GeoIP
    database cannot place. ``GeoIP.country_code`` is deliberately not used:
    it falls back to the CONTINENT code when the country is unknown."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if not addr.is_global:
        return None
    return GeoIP(ip).country.iso_code or None


class ResUsers(models.Model):
    _inherit = "res.users"

    reza_geolock_exempt = fields.Boolean(
        string="Allow sign-in from any country",
        groups="reza_login_geolock.group_geolock_manager",
        help="Exempt this user from the staff sign-in geolock, e.g. while travelling "
             "or for an integration that runs from overseas.",
    )

    def _reza_geolock_check(self, channel):
        """Refuse (or record) a staff sign-in from outside the allowed countries.

        Called only after the credentials have been accepted, so a wrong
        password is never recorded here, and only for internal users.

        This sits on every sign-in and every RPC call, so a fault in it lets
        the person in and is logged; only the deliberate refusal propagates."""
        try:
            self._reza_geolock_check_inner(channel)
        except AccessDenied:
            raise
        except Exception:                                    # noqa: BLE001
            _logger.exception("Staff sign-in geolock: check failed, sign-in allowed")

    def _reza_geolock_check_inner(self, channel):
        client = _client()
        if not client:
            return
        ip, user_agent = client
        params = self.env["ir.config_parameter"].sudo()
        mode = params.get_param(PARAM_MODE, "report")
        if mode not in ("report", "block"):
            return
        # Core calls _check_credentials on an EMPTY recordset for a password
        # re-check (change_password, the portal /my/security and
        # /my/deactivate_account pages); the user is then the env user.
        user = self if len(self) == 1 else self.env.user
        if len(user) != 1:
            return
        user = user.sudo()
        if user.share or user.reza_geolock_exempt:
            return
        country = _country_of(ip)
        if country is None:
            return
        allowed = {c.strip().upper() for c in (params.get_param(PARAM_COUNTRIES) or "AU").split(",") if c.strip()}
        if country in allowed:
            return
        action = "blocked" if mode == "block" else "would_block"
        _logger.warning("Staff sign-in geolock: %s login:%s from %s (%s) via %s",
                        action, user.login, ip, country, channel)
        self._reza_geolock_record({
            "user_id": user.id,
            "login": user.login,
            "ip": ip,
            "country": country,
            "channel": channel,
            "action": action,
            "user_agent": user_agent[:250],
        })
        if mode == "block":
            raise AccessDenied(self.env._(
                "Staff sign-in is not allowed from this country (%(country)s). "
                "Contact IT if you need access while away.", country=country))

    def _reza_geolock_record(self, vals):
        """Write the event on its own cursor.

        The refused sign-in raises AccessDenied, which rolls back the request's
        transaction, and RPC requests may run on a read-only cursor; either
        would lose the record. Under a running test the test's own cursor is
        used, so nothing is committed outside the test."""
        def write(env):
            events = env["reza.login.geolock.event"]
            since = fields.Datetime.now() - EVENT_QUIET
            if events.search_count([
                ("user_id", "=", vals["user_id"]), ("ip", "=", vals["ip"]),
                ("channel", "=", vals["channel"]), ("action", "=", vals["action"]),
                ("create_date", ">=", since),
            ]):
                return
            events.create(vals)

        try:
            # Under a TransactionCase the test's own cursor is used, so nothing
            # is committed outside the test. Under an HttpCase the request
            # already runs on a TestCursor and registry.cursor() is patched to
            # hand out another one over the same transaction.
            if odoo_module.current_test and type(self.env.cr).__name__ != "TestCursor":
                write(self.env(su=True))
                return
            if odoo_module.current_test and self.env.cr.readonly:
                # Odoo 18 test harness only: opening a read/write TestCursor
                # from a read-only one (e.g. /web/dataset/call_kw on a read
                # method) raises after taking the test lock and never releases
                # it, which hangs the rest of the test run. Outside tests
                # registry.cursor() is an independent read/write cursor.
                _logger.info("Staff sign-in geolock: event not recorded (read-only test cursor)")
                return
            with self.env.registry.cursor() as cr:
                write(api.Environment(cr, SUPERUSER_ID, {}))
        except Exception:                                    # noqa: BLE001
            _logger.exception("Staff sign-in geolock: could not record the event")

    def _check_credentials(self, credential, env):
        auth_info = super()._check_credentials(credential, env)
        interactive = (env or {}).get("interactive", True)
        self._reza_geolock_check("web" if interactive else "rpc")
        return auth_info

    @classmethod
    def check(cls, db, uid, passwd):
        # The parent is ormcached on (uid, passwd), so after the first RPC call
        # it no longer reaches _check_credentials. Check the address on every
        # call, outside the cache. In Odoo 18 this is a classmethod with no
        # environment (19 renamed it _check_uid_passwd on an env), so the check
        # needs a cursor of its own, opened only when an RPC client is known.
        super().check(db, uid, passwd)
        if not _client():
            return
        try:
            cr = cls.pool.cursor()
        except Exception:                                    # noqa: BLE001
            _logger.exception("Staff sign-in geolock: check failed, sign-in allowed")
            return
        with contextlib.closing(cr):
            env = api.Environment(cr, uid, {})
            env[cls._name].browse(uid)._reza_geolock_check("rpc")


class ResUsersApikeys(models.Model):
    _inherit = "res.users.apikeys"

    def _check_credentials(self, *, scope, key):
        uid = super()._check_credentials(scope=scope, key=key)
        if uid and scope == "rpc":
            # Bearer-token routes (auth='bearer', e.g. /json/1): ir.http only
            # calls this method.
            self.env["res.users"].browse(uid)._reza_geolock_check("apikey")
        return uid
