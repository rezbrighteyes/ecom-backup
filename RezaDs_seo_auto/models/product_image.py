import logging
from odoo import api, models

_logger = logging.getLogger(__name__)


class ProductImage(models.Model):
    _inherit = 'product.image'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._set_image_alt()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'product_tmpl_id' in vals:
            for record in self:
                record._set_image_alt()
        return res

    def _set_image_alt(self):
        self.ensure_one()
        if not self.product_tmpl_id:
            return
        product = self.product_tmpl_id
        parts = [product.name or '']
        if getattr(product, 'feed_brand_id', False) and product.feed_brand_id:
            parts.insert(0, product.feed_brand_id.name)
        alt_text = ' - '.join(parts)
        if self.name and self.name == alt_text:
            return
        try:
            super(ProductImage, self).write({'name': alt_text})
        except Exception as e:
            _logger.warning('Could not set image alt for product %s: %s', product.name, e)

    def bulk_fix_alt_text(self):
        images = self.search([])
        count = 0
        for img in images:
            if not img.product_tmpl_id:
                continue
            product = img.product_tmpl_id
            parts = [product.name or '']
            if getattr(product, 'feed_brand_id', False) and product.feed_brand_id:
                parts.insert(0, product.feed_brand_id.name)
            alt_text = ' - '.join(parts)
            if img.name != alt_text:
                img.write({'name': alt_text})
                count += 1
                if count % 100 == 0:
                    self.env.cr.commit()
                    _logger.info('Alt text updated: %s images so far', count)
        self.env.cr.commit()
        _logger.info('Alt text bulk fix done: %s images updated', count)
        return count
