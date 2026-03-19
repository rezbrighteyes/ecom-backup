import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

SEO_SCORE_SELECTION = [
    ('0', '0/5'),
    ('1', '1/5'),
    ('2', '2/5'),
    ('3', '3/5'),
    ('4', '4/5'),
    ('5', '5/5'),
]


class ProductTemplateSeoHealth(models.Model):
    _inherit = 'product.template'

    seo_score = fields.Integer(
        string='SEO Score',
        compute='_compute_seo_score',
        store=True,
    )
    seo_score_display = fields.Selection(
        SEO_SCORE_SELECTION,
        string='SEO Rating',
        compute='_compute_seo_score',
        store=True,
    )
    seo_issues = fields.Char(
        string='SEO Issues',
        compute='_compute_seo_score',
        store=True,
    )
    seo_has_title = fields.Boolean(
        string='Has SEO Title',
        compute='_compute_seo_score',
        store=True,
    )
    seo_has_description = fields.Boolean(
        string='Has Meta Description',
        compute='_compute_seo_score',
        store=True,
    )
    seo_has_slug = fields.Boolean(
        string='Has URL Slug',
        compute='_compute_seo_score',
        store=True,
    )
    seo_has_sku = fields.Boolean(
        string='Has SKU',
        compute='_compute_seo_score',
        store=True,
    )
    seo_has_content = fields.Boolean(
        string='Has eCommerce Description',
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

            has_title = bool(record.website_meta_title and record.website_meta_title != record.name)
            has_desc = bool(record.website_meta_description and len(record.website_meta_description) >= 50)
            has_slug = bool(record.seo_name)
            has_content = bool(record.description_ecommerce)
            has_sku = bool(record.default_code)

            if has_title:
                score += 1
            else:
                issues.append('Title')

            if has_desc:
                score += 1
            elif record.website_meta_description:
                issues.append('Short description')
            else:
                issues.append('Description')

            if has_slug:
                score += 1
            else:
                issues.append('Slug')

            if has_content:
                score += 1
            else:
                issues.append('Content')

            if has_sku:
                score += 1
            else:
                issues.append('SKU')

            record.seo_score = score
            record.seo_score_display = str(score)
            record.seo_issues = ', '.join(issues) if issues else ''
            record.seo_has_title = has_title
            record.seo_has_description = has_desc
            record.seo_has_slug = has_slug
            record.seo_has_sku = has_sku
            record.seo_has_content = has_content
