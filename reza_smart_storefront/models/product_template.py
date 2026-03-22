from datetime import date, timedelta
from odoo import models

SHIPPING_THRESHOLDS = {
    'Mangrove Jacks': 69,
    'WhatYouNeed': 150,
    'ecomsuperstore': 150,
    'Sunglass Superstore': 150,
}
DEFAULT_SHIPPING_THRESHOLD = 150


class ProductTemplateSF(models.Model):
    _inherit = 'product.template'

    def _sf_get_delivery_date(self, days=3):
        today = date.today()
        # If ordered on weekend, start counting from Monday
        if today.weekday() == 5:  # Saturday
            today += timedelta(days=2)
        elif today.weekday() == 6:  # Sunday
            today += timedelta(days=1)

        # Count only business days
        business_days = 0
        delivery = today
        while business_days < days:
            delivery += timedelta(days=1)
            if delivery.weekday() < 5:  # Mon-Fri
                business_days += 1

        return delivery.strftime('%A %d %B')

    def _sf_get_shipping_threshold(self):
        try:
            website = self.env['website'].get_current_website()
            return SHIPPING_THRESHOLDS.get(website.name, DEFAULT_SHIPPING_THRESHOLD)
        except Exception:
            return DEFAULT_SHIPPING_THRESHOLD

    def _sf_get_stock_qty(self):
        self.ensure_one()
        product_sudo = self.sudo()
        if getattr(product_sudo, 'allow_out_of_stock_order', False):
            return 999
        variant_ids = product_sudo.product_variant_ids.ids
        if not variant_ids:
            return 0
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', 'in', variant_ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ])
        return int(sum(quants.mapped('quantity')))

    def _sf_get_stock_message(self):
        self.ensure_one()
        qty = self._sf_get_stock_qty()
        if qty <= 0:
            return ''
        if qty <= 3:
            return 'Only %d left in stock!' % qty
        return ''

    def _sf_get_cross_sells(self, limit=4):
        self.ensure_one()
        try:
            website = self.env['website'].get_current_website()
            company = website.company_id
            website_id = website.id
        except Exception:
            company = self.env.company
            website_id = False

        domain = [
            ('website_published', '=', True),
            ('sale_ok', '=', True),
            ('id', '!=', self.id),
            ('company_id', 'in', [company.id, False]),
        ]

        if website_id:
            domain.append(('website_id', 'in', [website_id, False]))

        if self.public_categ_ids:
            domain.append(('public_categ_ids', 'in', self.public_categ_ids.ids))

        products = self.env['product.template'].sudo().search(domain, limit=limit * 5)

        # Filter only products that are in stock
        in_stock = products.filtered(lambda p: p._sf_is_available())

        price = self.list_price
        similar = in_stock.filtered(
            lambda p: price * 0.3 <= p.list_price <= price * 3
        )
        if len(similar) < limit:
            similar = in_stock
        return similar[:limit]

    def _sf_is_available(self):
        self.ensure_one()
        if getattr(self, 'allow_out_of_stock_order', False):
            return True
        variant_ids = self.sudo().product_variant_ids.ids
        if not variant_ids:
            return False
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', 'in', variant_ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ], limit=1)
        return bool(quants)
