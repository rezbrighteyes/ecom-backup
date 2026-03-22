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
        if today.weekday() == 5:
            today += timedelta(days=2)
        elif today.weekday() == 6:
            today += timedelta(days=1)

        business_days = 0
        delivery = today
        while business_days < days:
            delivery += timedelta(days=1)
            if delivery.weekday() < 5:
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

    def _sf_is_available(self):
        self.ensure_one()
        if getattr(self, 'allow_out_of_stock_order', False):
            return True
        variant_ids = self.sudo().product_variant_ids.ids
        if not variant_ids:
            return False
        self.env.cr.execute("""
            SELECT 1 FROM stock_quant sq
            JOIN stock_location sl ON sl.id = sq.location_id
            WHERE sq.product_id IN %s
            AND sl.usage = 'internal'
            AND sq.quantity > 0
            LIMIT 1
        """, (tuple(variant_ids),))
        return bool(self.env.cr.fetchone())

    def _sf_get_cross_sells(self, limit=4):
        self.ensure_one()
        try:
            website = self.env['website'].get_current_website()
            website_id = website.id
        except Exception:
            website_id = False

        if not website_id:
            return self.env['product.template']

        # Only products explicitly assigned to this website
        domain = [
            ('website_published', '=', True),
            ('sale_ok', '=', True),
            ('id', '!=', self.id),
            ('website_id', '=', website_id),
        ]

        # Try same public category first
        if self.public_categ_ids:
            cat_domain = domain + [('public_categ_ids', 'in', self.public_categ_ids.ids)]
            products = self.env['product.template'].sudo().search(cat_domain, limit=limit * 5)
            in_stock = products.filtered(lambda p: p._sf_is_available())
            if in_stock:
                price = self.list_price
                similar = in_stock.filtered(lambda p: price * 0.3 <= p.list_price <= price * 3)
                if len(similar) >= limit:
                    return similar[:limit]
                return in_stock[:limit]

        # Fallback: any product on this website that's in stock
        products = self.env['product.template'].sudo().search(domain, limit=limit * 5)
        in_stock = products.filtered(lambda p: p._sf_is_available())
        return in_stock[:limit]
