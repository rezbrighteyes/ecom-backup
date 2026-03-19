import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class ProductTemplateSeoHealth(models.Model):
    _inherit = 'product.template'

    seo_score = fields.Integer(
        string='SEO Score',
        compute='_compute_seo_score',
        store=True,
    )
    seo_issues = fields.Char(
        string='SEO Issues',
        compute='_compute_seo_score',
        store=True,
    )

    @api.depends(
        'website_meta_title', 'website_meta_description',
        'seo_name', 'website_meta_keywords',
        'description_ecommerce', 'default_code',
        'website_published',
    )
    def _compute_seo_score(self):
        for record in self:
            score = 0
            issues = []

            if record.website_meta_title and record.website_meta_title != record.name:
                score += 1
            else:
                issues.append('No optimized title')

            if record.website_meta_description and len(record.website_meta_description) >= 50:
                score += 1
            elif record.website_meta_description:
                issues.append('Description too short')
            else:
                issues.append('No meta description')

            if record.seo_name:
                score += 1
            else:
                issues.append('No URL slug')

            if record.description_ecommerce:
                score += 1
            else:
                issues.append('No ecommerce description')

            if record.default_code:
                score += 1
            else:
                issues.append('No SKU')

            record.seo_score = score
            record.seo_issues = ', '.join(issues) if issues else 'All good'
