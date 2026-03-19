import logging
from odoo import fields, models

_logger = logging.getLogger(__name__)


class SeoRegenerateWizard(models.TransientModel):
    _name = 'seo.regenerate.wizard'
    _description = 'Regenerate SEO Fields'

    regenerate_title = fields.Boolean(string='SEO Title', default=True)
    regenerate_slug = fields.Boolean(string='URL Slug', default=True)
    regenerate_description = fields.Boolean(string='Meta Description', default=True)
    regenerate_keywords = fields.Boolean(string='Meta Keywords', default=True)
    regenerate_image_alt = fields.Boolean(string='Image Alt Text', default=True)
    overwrite_existing = fields.Boolean(
        string='Overwrite existing values',
        default=False,
        help='If checked, existing SEO values will be replaced. If unchecked, only empty fields will be filled.',
    )
    product_count = fields.Integer(string='Products Selected', compute='_compute_product_count')

    def _compute_product_count(self):
        for record in self:
            record.product_count = len(self.env.context.get('active_ids', []))

    def action_regenerate(self):
        product_ids = self.env.context.get('active_ids', [])
        if not product_ids:
            return {'type': 'ir.actions.act_window_close'}

        products = self.env['product.template'].browse(product_ids)
        count = 0

        for product in products:
            updates = {}

            if self.regenerate_title and (self.overwrite_existing or not product.website_meta_title):
                name_part = product.name[:45] if len(product.name) > 45 else product.name
                updates['website_meta_title'] = ('%s | Buy Online' % name_part)[:60]

            if self.regenerate_slug and (self.overwrite_existing or not product.seo_name):
                from odoo.addons.RezaDs_seo_auto.models.product_template import _make_slug
                updates['seo_name'] = _make_slug(product.name)

            if self.regenerate_description and (self.overwrite_existing or not product.website_meta_description):
                from odoo.addons.RezaDs_seo_auto.models.product_template import _extract_seo_description
                desc = _extract_seo_description(product.description_ecommerce)
                if desc:
                    updates['website_meta_description'] = desc

            if self.regenerate_keywords and (self.overwrite_existing or not product.website_meta_keywords):
                keywords = []
                if getattr(product, 'feed_brand_id', False) and product.feed_brand_id:
                    keywords.append(product.feed_brand_id.name)
                if product.categ_id:
                    keywords.append(product.categ_id.name)
                if getattr(product, 'tag_ids', False):
                    keywords += product.tag_ids.mapped('name')
                keywords.append(product.name)
                updates['website_meta_keywords'] = ', '.join(keywords)

            if updates:
                product.write(updates)
                count += 1

            if self.regenerate_image_alt:
                for img in product.product_template_image_ids:
                    parts = [product.name or '']
                    if getattr(product, 'feed_brand_id', False) and product.feed_brand_id:
                        parts.insert(0, product.feed_brand_id.name)
                    img.write({'name': ' - '.join(parts)})

            if count % 100 == 0 and count > 0:
                self.env.cr.commit()

        self.env.cr.commit()
        _logger.info('SEO Wizard: %s products updated', count)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'SEO Regenerated',
                'message': '%s products updated successfully.' % count,
                'type': 'success',
                'sticky': False,
            }
        }
