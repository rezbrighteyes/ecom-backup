# -*- coding: utf-8 -*-

from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def should_print_delivery_address(self):
        self.ensure_one()
        if self.sale_id and self.sale_id.partner_invoice_id:
            return True
        else:
            super(StockPicking, self).should_print_delivery_address()
