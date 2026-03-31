import logging

_logger = logging.getLogger(__name__)

WEBSITE_ID = 5
BASE_PRODUCT_VIEW_KEY = 'website_sale.product'


def _apply_scoping(env):
    website = env['website'].browse(WEBSITE_ID)
    if not website.exists() or website.name != 'Sunglass Superstore':
        _logger.error(
            'sunglass_superstore_product_page: website id=%d not found.',
            WEBSITE_ID,
        )
        return

    # Prefer website-specific parent (id=5291 created by website editor)
    parent = env['ir.ui.view'].search([
        ('key', '=', BASE_PRODUCT_VIEW_KEY),
        ('website_id', '=', WEBSITE_ID),
    ], limit=1)

    if not parent:
        parent = env['ir.ui.view'].search([
            ('key', '=', BASE_PRODUCT_VIEW_KEY),
            ('website_id', '=', False),
        ], limit=1)

    if not parent:
        _logger.error(
            'sunglass_superstore_product_page: website_sale.product not found.'
        )
        return

    views = env['ir.ui.view'].search([
        ('key', 'like', 'sunglass_superstore_product_page.%')
    ])
    views.write({
        'website_id': WEBSITE_ID,
        'inherit_id': parent.id,
    })
    _logger.info(
        'sunglass_superstore_product_page: scoped %d views → '
        'website_id=%d inherit_id=%d',
        len(views), WEBSITE_ID, parent.id,
    )


def post_init_hook(env):
    _apply_scoping(env)


def post_update_hook(env):
    _apply_scoping(env)
