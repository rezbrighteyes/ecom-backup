# -*- coding: utf-8 -*-
from odoo import _, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_reza_unable_to_supply(self):
        """Open the Cannot Supply wizard. Public: it is a button target."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Cannot Supply"),
            "res_model": "reza.unable.supply.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_order_id": self.id},
        }
