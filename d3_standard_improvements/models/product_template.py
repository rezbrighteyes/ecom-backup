# -*- coding: utf-8 -*-

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    hide_sales_price = fields.Boolean("Hide Sales Price?")

    def _get_additionnal_combination_info(
        self, product_or_template, quantity, date, website
    ):
        combination_info = super(
            ProductTemplate, self
        )._get_additionnal_combination_info(
            product_or_template, quantity, date, website
        )
        if self.hide_sales_price and not combination_info.get(
            "prevent_zero_price_sale"
        ):
            combination_info.update({"prevent_zero_price_sale": True})
        return combination_info

    def _get_sales_prices(self, website):
        res = super(ProductTemplate, self)._get_sales_prices(website)
        for template in self.filtered("hide_sales_price"):
            template_price_vals = res[template.id]
            if template_price_vals.get("price_reduce"):
                template_price_vals.update({"price_reduce": 0})
        return res
