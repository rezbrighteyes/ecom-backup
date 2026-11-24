from odoo import fields, models


class RezaRmaReason(models.Model):
    _name = "reza.rma.reason"
    _description = "RMA Return Reason"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(string="Code")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    requires_attachment = fields.Boolean(
        default=False,
        help="If enabled, the portal form requires at least one photo uploaded.",
    )
    customer_selectable = fields.Boolean(
        default=True,
        help="If disabled, this reason is hidden from the portal dropdown.",
    )
    reza_freight_refundable = fields.Boolean(
        string="Freight Refundable",
        default=False,
        help="When enabled, shipping/freight lines are included in the credit note for this reason (e.g. wrong item received). By default freight is excluded.",
    )
    reza_return_fee_waived = fields.Boolean(
        string="Waive Return Shipping Fee",
        default=False,
    )
    allowed_resolution = fields.Selection(
        [
            ("any", "Any"),
            ("refund", "Refund Only"),
            ("store_credit", "Store Credit Only"),
            ("exchange", "Exchange Only"),
        ],
        required=True,
        default="any",
    )
    default_disposition = fields.Selection(
        [
            ("restock", "Restock"),
            ("refurbish", "Refurbish"),
            ("quarantine", "Quarantine"),
            ("discard", "Discard"),
            ("return_customer", "Return to Customer"),
        ],
        default="restock",
    )

    _code_unique = models.Constraint(
        'UNIQUE(code)',
        "Reason code must be unique.",
    )
