from odoo import fields, models


class RezaLoginGeolockEvent(models.Model):
    _name = "reza.login.geolock.event"
    _description = "Staff sign-in from outside the allowed countries"
    _order = "create_date desc, id desc"
    _rec_name = "login"

    user_id = fields.Many2one("res.users", string="User", ondelete="cascade", index=True)
    login = fields.Char(required=True)
    ip = fields.Char(string="IP Address")
    country = fields.Char(help="ISO country code from the GeoIP database.")
    channel = fields.Selection(
        [("web", "Web login"), ("rpc", "XML-RPC / JSON-RPC"), ("apikey", "API key (bearer)"),
         ("session", "Open session")],
        required=True,
    )
    action = fields.Selection(
        [("blocked", "Blocked"), ("would_block", "Would block (report only)")],
        required=True,
    )
    user_agent = fields.Char()
