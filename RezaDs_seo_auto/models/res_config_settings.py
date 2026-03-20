from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    seo_meta_title_template = fields.Char(
        string='Meta Title Template',
        config_parameter='rezads_seo.meta_title_template',
    )
    seo_default_brand = fields.Char(
        string='Default Brand Name',
        config_parameter='rezads_seo.default_brand',
    )
    seo_enable_schema = fields.Boolean(
        string='Enable Product Schema',
        config_parameter='rezads_seo.enable_schema',
    )
    seo_enable_breadcrumbs = fields.Boolean(
        string='Enable Breadcrumb Schema',
        config_parameter='rezads_seo.enable_breadcrumbs',
    )
    seo_enable_noindex = fields.Boolean(
        string='Enable Auto Noindex',
        config_parameter='rezads_seo.enable_noindex',
    )
    seo_enable_auto_title = fields.Boolean(
        string='Enable Auto SEO Title',
        config_parameter='rezads_seo.enable_auto_title',
    )
    seo_enable_auto_slug = fields.Boolean(
        string='Enable Auto URL Slug',
        config_parameter='rezads_seo.enable_auto_slug',
    )
    seo_enable_auto_description = fields.Boolean(
        string='Enable Auto Meta Description',
        config_parameter='rezads_seo.enable_auto_description',
    )
    seo_enable_auto_keywords = fields.Boolean(
        string='Enable Auto Keywords',
        config_parameter='rezads_seo.enable_auto_keywords',
    )
    seo_enable_auto_image_alt = fields.Boolean(
        string='Enable Auto Image Alt Text',
        config_parameter='rezads_seo.enable_auto_image_alt',
    )
    seo_enable_redirects = fields.Boolean(
        string='Enable 301 Redirects',
        config_parameter='rezads_seo.enable_redirects',
    )
