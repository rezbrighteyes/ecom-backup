"""Rename the 'hats' category to 'headwear'.

"Headwear" is what the group calls the category and it covers caps, beanies and
visors as well as hats — MJHat is one range of several. A selection value that
no longer exists in the field is not migrated by Odoo: the rows keep the old
string, nothing matches it, and the category silently stops appearing on every
page that had it.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        UPDATE product_tag
           SET stockist_category = 'headwear'
         WHERE stockist_category = 'hats'
    """)
    _logger.info("website_stockist: moved %s tags from 'hats' to 'headwear'",
                 cr.rowcount)
