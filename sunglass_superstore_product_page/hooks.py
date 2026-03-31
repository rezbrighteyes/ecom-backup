import logging

_logger = logging.getLogger(__name__)

WEBSITE_ID = 5
BASE_PRODUCT_VIEW_KEY = 'website_sale.product'
CONFLICTING_VIEW_KEYS = [
    'website_sale.product_quantity',  # id=5296 — replaced by our CTA
]


def _apply_scoping(env):
    # Find website-specific parent (full clone, no xmlid)
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
        _logger.error('sunglass_superstore_product_page: website_sale.product not found.')
        return

    # Scope our views to website_id=5 and correct parent
    views = env['ir.ui.view'].search([
        ('key', 'like', 'sunglass_superstore_product_page.%')
    ])
    views.write({'website_id': WEBSITE_ID, 'inherit_id': parent.id})
    _logger.info(
        'sunglass_superstore_product_page: scoped %d views → '
        'website_id=%d inherit_id=%d',
        len(views), WEBSITE_ID, parent.id,
    )

    # Deactivate conflicting website_id=5 views that override our templates
    for key in CONFLICTING_VIEW_KEYS:
        conflict = env['ir.ui.view'].search([
            ('key', '=', key),
            ('website_id', '=', WEBSITE_ID),
        ])
        if conflict:
            conflict.write({'active': False})
            _logger.info(
                'sunglass_superstore_product_page: deactivated conflicting view %s',
                key,
            )


def post_init_hook(env):
    _apply_scoping(env)


def post_update_hook(env):
    _apply_scoping(env)
