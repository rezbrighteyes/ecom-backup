import logging

_logger = logging.getLogger(__name__)

WEBSITE_ID = 5


def post_init_hook(env):
    website = env['website'].browse(WEBSITE_ID)
    if not website.exists() or website.name != 'Sunglass Superstore':
        _logger.error(
            'sunglass_superstore_product_page: website id=%d is not '
            'Sunglass Superstore — views not scoped.',
            WEBSITE_ID,
        )
        return
    views = env['ir.ui.view'].search([
        ('key', 'like', 'sunglass_superstore_product_page.%')
    ])
    views.write({'website_id': WEBSITE_ID})
    _logger.info(
        'sunglass_superstore_product_page: scoped %d views to website_id=%d',
        len(views), WEBSITE_ID,
    )
