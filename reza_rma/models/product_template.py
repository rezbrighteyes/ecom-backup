from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    rma_return_method = fields.Selection(
        [
            ("auspost", "Australia Post Returns Portal"),
            ("manual", "Manual — Warehouse Address"),
        ],
        string="RMA Return Method",
        default="auspost",
    )
    reza_non_returnable = fields.Boolean(
        string="Non-returnable / Final Sale",
        help="If enabled, this product cannot be returned from the portal.",
    )
    reza_return_policy_note = fields.Char(
        string="Return Policy Note",
        help="Short customer-facing note shown when the item is not returnable.",
    )
