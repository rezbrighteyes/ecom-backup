from odoo import api, fields, models, _
from itertools import product


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def get_selected_variants(self):
        variants = self.env['product.product']
        product_variants = self.product_variant_ids
        attribute_line_ids = self.attribute_line_ids.filtered(lambda x: x.show_in_website)
        if attribute_line_ids:
            cmb_list = [line.mapped('value_ids.id') for line in attribute_line_ids]
            combinations = list(map(list, product(*cmb_list)))
            for c in combinations:
                variant = self.env['product.product']
                for pv in product_variants:
                    if all(cc in pv.product_template_variant_value_ids.mapped('product_attribute_value_id.id') for
                           cc in c):
                        variant |= pv
                if variant:
                    variants |= variant[0]
        else:
            variants |= product_variants
        return variants


class Product(models.Model):
    _inherit = 'product.product'


    def _get_sales_prices(self, website):
        if not self:
            return {}

        pricelist = website.pricelist_id
        currency = website.currency_id
        fiscal_position = website.fiscal_position_id.sudo()
        date = fields.Date.context_today(self)

        pricelist_prices = pricelist._compute_price_rule(self, 1.0)
        comparison_prices_enabled = self.env.user.has_group('website_sale.group_product_price_comparison')

        res = {}
        for template in self:
            pricelist_price, pricelist_rule_id = pricelist_prices[template.id]

            product_taxes = template.sudo().taxes_id._filter_taxes_by_company(self.env.company)
            taxes = fiscal_position.map_tax(product_taxes)

            base_price = None
            template_price_vals = {
                'price_reduce': self.env['product.template']._apply_taxes_to_price(
                    pricelist_price, currency, product_taxes, taxes, template, website=website,
                ),
            }
            pricelist_item = template.env['product.pricelist.item'].browse(pricelist_rule_id)
            if pricelist_item._show_discount_on_shop():
                pricelist_base_price = pricelist_item._compute_price_before_discount(
                    product=template,
                    quantity=1.0,
                    date=date,
                    uom=template.uom_id,
                    currency=currency,
                )
                if currency.compare_amounts(pricelist_base_price, pricelist_price) == 1:
                    base_price = pricelist_base_price
                    template_price_vals['base_price'] = self.env['product.template']._apply_taxes_to_price(
                        base_price, currency, product_taxes, taxes, template, website=website,
                    )

            if not base_price and comparison_prices_enabled and template.compare_list_price:
                template_price_vals['base_price'] = template.currency_id._convert(
                    template.compare_list_price,
                    currency,
                    self.env.company,
                    date,
                    round=False,
                )

            res[template.id] = template_price_vals

        return res

    def _get_combination_info_variant(self, **kwargs):
        res = super()._get_combination_info_variant(**kwargs)
        combination = self.product_template_variant_value_ids
        variant_attributes = []
        for cmb in combination:
            variant_attributes.append([cmb.attribute_id.name, cmb.name])
        res['variant_attributes'] = variant_attributes
        return res

    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get('website_id'):
            for product in self:
                variant_display_name = product.display_name
                variant_names = []
                selected_attributes = product.product_tmpl_id.attribute_line_ids.filtered(lambda x: x.show_in_website)
                for vv in product.product_template_variant_value_ids:
                    if vv.attribute_id.id in selected_attributes.mapped('attribute_id.id'):
                        variant_names.append(vv.name)
                if variant_names:
                    variant_display_name = f"{product.name} ({', '.join(variant_names)})"
                product.display_name = variant_display_name



class ProductTemplateAttributeLine(models.Model):
    _inherit = 'product.template.attribute.line'

    show_in_website = fields.Boolean()
