import ipaddress

from odoo import api, fields, models
from odoo.exceptions import ValidationError

# Bumped on every change to the allow-list, and part of the open-session
# stamp in ir_http.py, so removing an address ends the sessions using it on
# their next request instead of when their address next changes.
PARAM_IPS_STAMP = "reza_login_geolock.ips_stamp"


class RezaLoginGeolockIp(models.Model):
    """An address or range that may sign in from outside the allowed countries.

    Added 17 Nov 2026 for staff working from a fixed line overseas (Paul
    Ingram's UK home broadband), where exempting the person outright would
    let their password work from any country. Optionally limited to named
    users. Only the Sign-in Geolock Manager group can see or edit the list."""
    _name = "reza.login.geolock.ip"
    _description = "Staff sign-in geolock: allowed IP address"
    _order = "name"

    name = fields.Char(
        string="IP Address or Range", required=True,
        help="One IPv4 or IPv6 address (86.152.3.45) or a range in CIDR form "
             "(2a00:23c7:d7db:2500::/56). Home broadband IPv6 is usually a /56 or "
             "/64 whose last part changes, so enter the range.")
    user_ids = fields.Many2many(
        "res.users", "reza_login_geolock_ip_user_rel", "ip_id", "user_id",
        string="Only For", domain=[("share", "=", False)],
        help="Leave empty to allow every staff user from this address.")
    note = fields.Char(help="Whose line this is and why it is allowed.")
    active = fields.Boolean(default=True)

    @api.model
    def _normalise(self, value):
        try:
            return str(ipaddress.ip_network((value or "").strip(), strict=False))
        except ValueError:
            raise ValidationError(self.env._(
                "'%(value)s' is not an IP address or a CIDR range.", value=value)) from None

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "name" in vals:
                vals["name"] = self._normalise(vals["name"])
        records = super().create(vals_list)
        self._bump()
        return records

    def write(self, vals):
        if "name" in vals:
            vals["name"] = self._normalise(vals["name"])
        res = super().write(vals)
        self._bump()
        return res

    def unlink(self):
        res = super().unlink()
        self._bump()
        return res

    @api.model
    def _bump(self):
        self.env["ir.config_parameter"].sudo().set_str(PARAM_IPS_STAMP, fields.Datetime.now().isoformat())

    @api.model
    def _reza_allows(self, ip, user):
        """True when an active entry covers this address for this user."""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for rec in self.sudo().search([]):
            try:
                net = ipaddress.ip_network(rec.name, strict=False)
            except ValueError:
                continue
            if addr.version == net.version and addr in net and (not rec.user_ids or user in rec.user_ids):
                return True
        return False
