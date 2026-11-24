import json
import uuid

from odoo import fields, models


class RezaRmaPendingSubmission(models.Model):
    _name = "reza.rma.pending.submission"
    _description = "Pending Return Postage Payment"
    _order = "create_date desc"

    token = fields.Char(
        required=True,
        index=True,
        copy=False,
        default=lambda self: uuid.uuid4().hex,
    )
    sale_order_id = fields.Many2one("sale.order", required=True, ondelete="cascade")
    submission_json = fields.Text(required=True)
    amount = fields.Float(required=True, digits=(10, 2))
    currency_id = fields.Many2one("res.currency", required=True)
    state = fields.Selection(
        [("pending", "Pending"), ("done", "Done"), ("expired", "Expired")],
        default="pending",
        required=True,
    )

    @property
    def payment_reference(self):
        return f"RET-POST-{self.token[:8].upper()}"

    def get_submission_data(self):
        return json.loads(self.submission_json)
