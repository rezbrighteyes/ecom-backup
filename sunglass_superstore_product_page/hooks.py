import logging
_logger = logging.getLogger(__name__)

SS_WEBSITE_NAME = 'Sunglass Superstore'

# These are the actual XML ids as Odoo stores them (module.template_id)
SS_VIEW_KEYS = [
    'sunglass_superstore_product_page.product_cta_wrapper',
    'sunglass_superstore_product_page.product_collection_label',
    'sunglass_superstore_product_page.product_accordion_custom',
    'sunglass_superstore_product_page.product_price_badge',
    'sunglass_superstore_product_page.product_payment_methods',
    'sunglass_superstore_product_page.ss_stock_urgency',
    'sunglass_superstore_product_page.ss_trust_badges',
    'sunglass_superstore_product_page.ss_product_description_crosssells',
]


def _scope_views_to_website(env):
    website = env['website'].sudo().search(
        [('name', '=', SS_WEBSITE_NAME)], limit=1
    )
    if not website:
        _logger.warning(
            'sunglass_superstore_product_page: website "%s" not found',
            SS_WEBSITE_NAME
        )
        return
    views = env['ir.ui.view'].with_context(active_test=False).search([
        ('key', 'in', SS_VIEW_KEYS),
    ])
    _logger.info(
        'sunglass_superstore_product_page: found %d views to scope', len(views)
    )
    for view in views:
        if view.website_id.id != website.id:
            view.website_id = website.id
            _logger.info('Scoped view %s → website_id=%s', view.key, website.id)


def post_init_hook(env):
    _scope_views_to_website(env)


def post_update_hook(env):
    _scope_views_to_website(env)
