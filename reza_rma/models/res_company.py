from datetime import timedelta

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    reza_rma_return_window_days = fields.Integer(
        string="RMA Return Window (Days)",
        default=30,
        help="Standard number of days customers have to start a return.",
    )
    reza_rma_holiday_deadline = fields.Date(
        string="Holiday Return Deadline",
        help=(
            "Optional override date used during peak seasons. If this date is later "
            "than the normal deadline, customers may return until this date instead."
        ),
    )
    reza_rma_store_credit_bonus_percent = fields.Float(
        string="First Return Store Credit Bonus %",
        default=10.0,
        help="Bonus percentage offered on the first approved store-credit return.",
    )
    reza_rma_disclaimer_text = fields.Text(
        string="Returns Policy Disclaimer",
        default=(
            "I confirm that the item(s) being returned are unused, unworn, and in original condition "
            "with all tags attached and in original packaging. I have read and agree to the returns policy. "
            "I understand that the cost of return shipping will be deducted from my refund."
        ),
    )
    reza_rma_return_shipping_fee = fields.Float(
        string="Default Return Shipping Fee",
        digits=(16, 2),
        default=9.95,
        help="Default return shipping cost deducted from customer refunds (shown on the portal).",
    )
    reza_rma_return_shipping_product_id = fields.Many2one(
        "product.product",
        string="Return Shipping Charge Product",
        domain="[('type', '=', 'service')]",
        check_company=True,
        help="Used as the visible deduction line on scoped return credit notes.",
    )
    reza_rma_refund_operation_id = fields.Many2one(
        "rma.operation",
        string="Refund / Store Credit RMA Operation",
        help="OCA RMA operation used for refund and store-credit requests.",
    )
    reza_rma_exchange_operation_id = fields.Many2one(
        "rma.operation",
        string="Exchange RMA Operation",
        help="OCA RMA operation used for exchange requests.",
    )
    reza_rma_store_credit_program_id = fields.Many2one(
        "loyalty.program",
        string="Ecommerce Store Credit Program",
        domain="[('program_type', '=', 'gift_card'), ('ecommerce_ok', '=', True)]",
        check_company=True,
    )
    reza_rma_return_carrier_id = fields.Many2one(
        "delivery.carrier",
        string="Return Starshipit Carrier",
        domain="[('active', '=', True)]",
        check_company=True,
        help="Explicit carrier used for return labels. The selected carrier must expose the loaded Starshipit return-label API.",
    )
    reza_rma_exchange_hold_hours = fields.Integer(
        string="Exchange Hold Hours",
        default=48,
    )
    reza_rma_enable_labels = fields.Boolean(
        string="Enable Automatic Return Labels",
        default=False,
        help="Enable only after Starshipit is installed, configured, and tested in staging.",
    )
    reza_rma_enable_refunds = fields.Boolean(
        string="Enable Scoped Return Refunds",
        default=False,
        help="Enable only after accounting signs off scoped credit note totals in staging.",
    )
    reza_rma_enable_exchanges = fields.Boolean(
        string="Enable Exchanges",
        default=False,
        help="Enable only after exchange stock and payment gates pass staging tests.",
    )

    def reza_get_rma_return_deadline(self, order_date):
        self.ensure_one()
        if not order_date:
            return False
        deadline = order_date + timedelta(days=max(self.reza_rma_return_window_days, 0))
        if self.reza_rma_holiday_deadline and self.reza_rma_holiday_deadline > deadline:
            deadline = self.reza_rma_holiday_deadline
        return deadline
