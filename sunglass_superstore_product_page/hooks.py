import logging
_logger = logging.getLogger(__name__)

SS_WEBSITE_NAME = 'Sunglass Superstore'


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
        ('key', 'like', 'sunglass_superstore_product_page.'),
    ])

    _logger.info(
        'sunglass_superstore_product_page: scoping %d views to website %s',
        len(views), website.id
    )

    for view in views:
        if view.website_id.id != website.id:
            view.website_id = website.id
            _logger.info('Scoped view %s → website_id=%s', view.key, website.id)


def post_init_hook(env):
    _scope_views_to_website(env)


def post_update_hook(env):
    _scope_views_to_website(env)
