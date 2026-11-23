from odoo import fields, models


class ActivityLog(models.Model):
    _inherit = "activity.log"

    action = fields.Selection(
        selection_add=[("geolock", "Geolock Refusal")],
        ondelete={"geolock": "cascade"},
    )
