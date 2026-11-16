# -*- coding: utf-8 -*-
from odoo import _, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # groups=base.group_user: website_sale lets portal users read sale orders
    # over call_kw, and these say nothing a customer needs.
    reza_exchange_origin_id = fields.Many2one(
        "sale.order", string="Exchange Of", copy=False, readonly=True, index="btree_not_null",
        groups="base.group_user",
        help="The delivered order this replacement was made for.")
    reza_exchange_ids = fields.One2many(
        "sale.order", "reza_exchange_origin_id", string="Replacement Orders",
        groups="base.group_user")
    reza_edbert_return_ids = fields.One2many(
        "reza.edbert.return", "sale_order_id", string="Edbert Returns",
        groups="base.group_user")
    reza_customer_refund_ids = fields.One2many(
        "reza.customer.refund", "sale_order_id", string="Customer Refunds",
        groups="base.group_user")

    def action_reza_exchange_shipped(self):
        """Open the Exchange (shipped) wizard. Public: it is a button target.
        The wizard re-checks rights itself."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Exchange (shipped)"),
            "res_model": "reza.exchange.shipped.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }

    def action_reza_refund_shipped(self):
        """Open the Refund (shipped) wizard. Public: it is a button target.
        The wizard re-checks rights itself."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Refund (shipped)"),
            "res_model": "reza.refund.shipped.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }
