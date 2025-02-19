# -*- coding: utf-8 -*-

from odoo import models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _get_contextual_price_tax_selection(self):
        if self.product_tmpl_id.hide_sales_price:
            return 0.0
        else:
            return super(ProductProduct, self)._get_contextual_price_tax_selection()
