from datetime import date, timedelta
from odoo import models


class ProductTemplateSF(models.Model):
    _inherit = 'product.template'

    def _sf_get_delivery_date(self, days=3):
        delivery = date.today() + timedelta(days=days)
        while delivery.weekday() >= 5:
            delivery += timedelta(days=1)
        return delivery.strftime('%A %d %B')

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

    def _sf_get_cross_sells(self, limit=6):
        self.ensure_one()
        try:
            website = self.env['website'].get_current_website()
            company = website.company_id
        except Exception:
            company = self.env.company

        domain = [
            ('website_published', '=', True),
            ('sale_ok', '=', True),
            ('id', '!=', self.id),
            ('company_id', 'in', [company.id, False]),
        ]
        if self.public_categ_ids:
            domain.append(('public_categ_ids', 'in', self.public_categ_ids.ids))

        products = self.env['product.template'].sudo().search(domain, limit=limit * 3)
        price = self.list_price
        similar = products.filtered(
            lambda p: price * 0.3 <= p.list_price <= price * 3
        )
        if len(similar) < limit:
            similar = products
        return similar[:limit]
