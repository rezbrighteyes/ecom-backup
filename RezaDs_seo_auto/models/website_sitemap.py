# -- coding: utf-8 --
# Copyright 2026 Reza Shiraz
# License LGPL-3.

from odoo import models


class ProductTemplateSitemap(models.Model):
    _inherit = 'product.template'

    def _get_sitemap_urls(self, query_string=None, canonical_params=None):
        """
        Stock-aware sitemap priority:
            qty > 10  → 1.0  fully stocked, crawl first
            qty 1-10  → 0.8  low stock but available
            qty = 0   → 0.1  out of stock, crawl last
        lastmod reflects write_date so Google sees stock changes fast.
        """
        root = super()._get_sitemap_urls(query_string, canonical_params)

        published = self.env['product.template'].sudo().search([
            ('website_published', '=', True),
            ('sale_ok', '=', True),
        ])

        result = []
        for product in published:
            qty = product.qty_available

            if qty > 10:
                priority = 1.0
            elif qty > 0:
                priority = 0.8
            else:
                priority = 0.1

            result.append({
                'loc': '/shop/%s' % product.website_slug,
                'priority': priority,
                'lastmod': product.write_date.strftime('%Y-%m-%d'),
            })

        return result


class StockMoveLastmod(models.Model):
    _inherit = 'stock.move.line'

    def write(self, vals):
        res = super().write(vals)
        if 'qty_done' in vals:
            for move in self:
                product = move.move_id.product_id.product_tmpl_id
                if product.website_published:
                    product.sudo().write({
                        'website_meta_title': product.website_meta_title or product.name
                    })
        return res
