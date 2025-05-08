# -*- coding: utf-8 -*-

from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def should_print_delivery_address(self):
        self.ensure_one()
        if self.sale_id and self.sale_id.partner_invoice_id:
            return True
        else:
            return (
                self.move_ids
                and (self.move_ids[0].partner_id or self.partner_id)
                and self._is_to_external_location()
            )
