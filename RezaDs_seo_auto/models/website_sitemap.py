import logging
from odoo import models

_logger = logging.getLogger(__name__)


class ProductTemplateSitemap(models.Model):
    _inherit = 'product.template'

    def _get_sitemap_urls(self, query_string=None, canonical_params=None):
        root = super()._get_sitemap_urls(query_string, canonical_params)

        published = self.env['product.template'].sudo().search([
            ('website_published', '=', True),
            ('sale_ok', '=', True),
        ])

        result = []
        for product in published:
            try:
                if product._is_in_stock():
                    priority = 1.0
                else:
                    priority = 0.1

                slug = product.seo_name or '%s-%s' % (product.name or '', product.id)
                result.append({
                    'loc': '/shop/%s' % slug,
                    'priority': priority,
                    'lastmod': product.write_date.strftime('%Y-%m-%d'),
                })
            except Exception as e:
                _logger.warning('Sitemap error for product %s: %s', product.id, e)

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
