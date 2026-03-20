from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    seo_meta_title_template = fields.Char(
        string='Meta Title Template',
        config_parameter='rezads_seo.meta_title_template',
        default='%(name)s | Buy Online',
        help='Use %(name)s for product name. Example: "%(name)s | Buy Online | My Store"',
    )
    seo_default_brand = fields.Char(
        string='Default Brand Name',
        config_parameter='rezads_seo.default_brand',
        help='Fallback brand name when product has no brand set. Leave empty to use website name.',
    )
    seo_enable_schema = fields.Boolean(
        string='Enable Product Schema',
        config_parameter='rezads_seo.enable_schema',
        default=True,
    )
    seo_enable_breadcrumbs = fields.Boolean(
        string='Enable Breadcrumb Schema',
        config_parameter='rezads_seo.enable_breadcrumbs',
        default=True,
    )
    seo_enable_noindex = fields.Boolean(
        string='Enable Auto Noindex',
        config_parameter='rezads_seo.enable_noindex',
        default=True,
        help='Automatically add noindex to unpublished or inactive products.',
    )
    seo_enable_auto_title = fields.Boolean(
        string='Enable Auto SEO Title',
        config_parameter='rezads_seo.enable_auto_title',
        default=True,
    )
    seo_enable_auto_slug = fields.Boolean(
        string='Enable Auto URL Slug',
        config_parameter='rezads_seo.enable_auto_slug',
        default=True,
    )
    seo_enable_auto_description = fields.Boolean(
        string='Enable Auto Meta Description',
        config_parameter='rezads_seo.enable_auto_description',
        default=True,
    )
    seo_enable_auto_keywords = fields.Boolean(
        string='Enable Auto Keywords',
        config_parameter='rezads_seo.enable_auto_keywords',
        default=True,
    )
    seo_enable_auto_image_alt = fields.Boolean(
        string='Enable Auto Image Alt Text',
        config_parameter='rezads_seo.enable_auto_image_alt',
        default=True,
    )
    seo_enable_redirects = fields.Boolean(
        string='Enable 301 Redirects',
        config_parameter='rezads_seo.enable_redirects',
        default=True,
        help='Auto-create 301 redirects when product URL slug changes.',
    )
