import logging
_logger = logging.getLogger(__name__)

EXCLUDE_WEBSITE_NAME = 'Sunglass Superstore'

SF_VIEW_KEYS = [
    'reza_smart_storefront.stock_urgency',
    'reza_smart_storefront.trust_badges',
    'reza_smart_storefront.product_description_crosssells',
]


def _scope_views_to_non_ss_websites(env):
    exclude = env['website'].sudo().search(
        [('name', '=', EXCLUDE_WEBSITE_NAME)], limit=1
    )
    all_websites = env['website'].sudo().search([])
    target_websites = all_websites - exclude
    if not target_websites:
        _logger.warning('reza_smart_storefront: no target websites found')
        return
    base_views = {}
    views = env['ir.ui.view'].with_context(active_test=False).search([
        ('key', 'in', SF_VIEW_KEYS),
    ])
    for view in views:
        base_views[view.key] = view
    for website in target_websites:
        for key, view in base_views.items():
            existing = env['ir.ui.view'].with_context(active_test=False).search([
                ('key', '=', key),
                ('website_id', '=', website.id),
            ])
            if not existing:
                view.copy({'website_id': website.id})
                _logger.info('Scoped %s to website_id=%s', key, website.id)
    for key, view in base_views.items():
        if not view.website_id:
            view.website_id = target_websites[0].id


def post_init_hook(env):
    _scope_views_to_non_ss_websites(env)


def post_update_hook(env):
    _scope_views_to_non_ss_websites(env)
