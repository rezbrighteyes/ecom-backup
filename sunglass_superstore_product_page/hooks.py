import logging

_logger = logging.getLogger(__name__)

WEBSITE_ID = 5
BASE_PRODUCT_VIEW_KEY = 'website_sale.product'


def post_init_hook(env):
    website = env['website'].browse(WEBSITE_ID)
    if not website.exists() or website.name != 'Sunglass Superstore':
        _logger.error(
            'sunglass_superstore_product_page: website id=%d not found.',
            WEBSITE_ID,
        )
        return

    # Find the website-specific override of website_sale.product for this website
    # (created by website editor — has no xmlid)
    website_specific_parent = env['ir.ui.view'].search([
        ('key', '=', BASE_PRODUCT_VIEW_KEY),
        ('website_id', '=', WEBSITE_ID),
    ], limit=1)

    # Fall back to the base view if no website-specific override exists
    if not website_specific_parent:
        website_specific_parent = env['ir.ui.view'].search([
            ('key', '=', BASE_PRODUCT_VIEW_KEY),
            ('website_id', '=', False),
        ], limit=1)

    if not website_specific_parent:
        _logger.error(
            'sunglass_superstore_product_page: cannot find website_sale.product view.',
        )
        return

    _logger.info(
        'sunglass_superstore_product_page: using parent view id=%d (website_id=%s)',
        website_specific_parent.id,
        website_specific_parent.website_id.id,
    )

    views = env['ir.ui.view'].search([
        ('key', 'like', 'sunglass_superstore_product_page.%')
    ])
    views.write({
        'website_id': WEBSITE_ID,
        'inherit_id': website_specific_parent.id,
    })
    _logger.info(
        'sunglass_superstore_product_page: scoped %d views to website_id=%d, inherit_id=%d',
        len(views), WEBSITE_ID, website_specific_parent.id,
    )
