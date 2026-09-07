"""Classify the ranges that already exist when upgrading into 3.0.0.

post_init_hook runs on install and never on upgrade, so on a database where the
module is already installed every tag would arrive with stockist_category unset.
That is worse than the codes it replaces: _range_groups() only shows classified
ranges, so the badges would disappear entirely rather than read "Sunglasses".
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["product.tag"]._seed_stockist_categories()
    classified = env["product.tag"].search_count(
        [("stockist_category", "!=", False)])
    unclassified = env["product.tag"].search_count(
        [("stockist_category", "=", False)])
    _logger.info(
        "website_stockist: classified %s product tags, %s left for a human "
        "(filter 'Needs a stockist category' on the tag list)",
        classified, unclassified,
    )
