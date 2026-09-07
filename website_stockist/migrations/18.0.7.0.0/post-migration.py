"""Create a content row per website for every existing stockist.

Without this the upgrade is silently lossy in a way nobody would notice for a
while: the resolver falls back to the record-level tag when no row exists, so
every page keeps working — and then the first time someone edits a row, that
stockist starts behaving differently from the rest for no visible reason.

Seeding the rows up front means what the site does is what the rows say, from
the first request after the upgrade.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    Content = env["website.stockist.content"]

    created = 0
    for stockist in env["website.stockist"].with_context(active_test=False).search([]):
        # An empty website_ids means "every website", which is the module's own
        # convention — see _get_published_domain.
        websites = stockist.website_ids or env["website"].search([])
        for website in websites:
            if Content.search_count([("stockist_id", "=", stockist.id),
                                     ("website_id", "=", website.id)]):
                continue
            Content.create({
                "stockist_id": stockist.id,
                "website_id": website.id,
                # Carried across, not re-derived: whatever the stockist was
                # tagged with is what that site was already showing.
                "stockist_tag_ids": [(6, 0, stockist.stockist_tag_ids.ids)],
            })
            created += 1
    _logger.info("website_stockist: created %s per-website content rows", created)
