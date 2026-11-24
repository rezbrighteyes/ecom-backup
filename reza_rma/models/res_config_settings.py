from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    reza_rma_return_window_days = fields.Integer(
        related="company_id.reza_rma_return_window_days",
        readonly=False,
    )
    reza_rma_holiday_deadline = fields.Date(
        related="company_id.reza_rma_holiday_deadline",
        readonly=False,
    )
    reza_rma_store_credit_bonus_percent = fields.Float(
        related="company_id.reza_rma_store_credit_bonus_percent",
        readonly=False,
    )
    reza_rma_disclaimer_text = fields.Text(
        related="company_id.reza_rma_disclaimer_text",
        readonly=False,
    )
    reza_rma_return_shipping_fee = fields.Float(
        related="company_id.reza_rma_return_shipping_fee",
        readonly=False,
    )
    reza_rma_return_shipping_product_id = fields.Many2one(
        related="company_id.reza_rma_return_shipping_product_id",
        readonly=False,
    )
    reza_rma_refund_operation_id = fields.Many2one(
        related="company_id.reza_rma_refund_operation_id",
        readonly=False,
    )
    reza_rma_exchange_operation_id = fields.Many2one(
        related="company_id.reza_rma_exchange_operation_id",
        readonly=False,
    )
    reza_rma_store_credit_program_id = fields.Many2one(
        related="company_id.reza_rma_store_credit_program_id",
        readonly=False,
    )
    reza_rma_return_carrier_id = fields.Many2one(
        related="company_id.reza_rma_return_carrier_id",
        readonly=False,
    )
    reza_rma_exchange_hold_hours = fields.Integer(
        related="company_id.reza_rma_exchange_hold_hours",
        readonly=False,
    )
    reza_rma_enable_labels = fields.Boolean(
        related="company_id.reza_rma_enable_labels",
        readonly=False,
    )
    reza_rma_enable_refunds = fields.Boolean(
        related="company_id.reza_rma_enable_refunds",
        readonly=False,
    )
    reza_rma_enable_exchanges = fields.Boolean(
        related="company_id.reza_rma_enable_exchanges",
        readonly=False,
    )
