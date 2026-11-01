from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    reza_geolock_mode = fields.Selection(
        [("off", "Off"), ("report", "Report only"), ("block", "Block")],
        string="Staff Sign-in Geolock",
        config_parameter="reza_login_geolock.mode",
        default="report",
    )
    reza_geolock_countries = fields.Char(
        string="Allowed Countries",
        config_parameter="reza_login_geolock.countries",
        default="AU",
        help="ISO country codes, comma separated, e.g. AU or AU,NZ.",
    )
