import logging

_logger = logging.getLogger(__name__)

WEBSITE_ID = 5
CONFLICTING_VIEW_KEYS = [
    'website_sale.product_quantity',
]


def _apply_scoping(env):
    # Scope our views to website_id=5
    views = env['ir.ui.view'].search([
        ('key', 'like', 'sunglass_superstore_product_page.%')
    ])
    views.write({'website_id': WEBSITE_ID})
    _logger.info(
        'sunglass_superstore_product_page: scoped %d views to website_id=%d',
        len(views), WEBSITE_ID,
    )

    # Deactivate conflicting website_id=5 views
    for key in CONFLICTING_VIEW_KEYS:
        conflict = env['ir.ui.view'].search([
            ('key', '=', key),
            ('website_id', '=', WEBSITE_ID),
        ])
        if conflict:
            conflict.write({'active': False})
            _logger.info(
                'sunglass_superstore_product_page: deactivated %s', key
            )


def post_init_hook(env):
    _apply_scoping(env)


def post_update_hook(env):
    _apply_scoping(env)
