"""Clear the stored stockist titles so the per-website generator can own them.

127 records were written with "Mangrove Jacks at <store>" in website_meta_title.
That string is static: on a second brand's site every one of those pages would
have carried the wrong brand in its title.

It also could not be overridden. website.layout prefers a stored
website_meta_title over anything computed, so _meta_title() would have been
silently beaten on every page that had one.

Clearing them is safe because nothing is lost: the generator produces the same
string on Mangrove Jacks — brand + " at " + store name — and produces the right
one everywhere else. A title somebody typed by hand belongs on the per-website
content row, which this does not touch.

These are TRANSLATED fields, so the write is done in the site's language.
Clearing en_US alone would leave the en_AU value in place and change nothing a
visitor sees.
"""
import logging

_logger = logging.getLogger(__name__)

GENERATED_PREFIXES = ("Mangrove Jacks at ",)


def migrate(cr, version):
    if not version:
        return
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    lang = env["website"].search([], limit=1).default_lang_id.code or "en_AU"
    stockists = env["website.stockist"].with_context(
        active_test=False, lang=lang).search([])

    cleared = kept = 0
    for stockist in stockists:
        title = (stockist.website_meta_title or "").strip()
        if not title:
            continue
        # Only clear what this module generated. Anything a person wrote is
        # theirs, and is left exactly where they put it.
        if title.startswith(GENERATED_PREFIXES):
            stockist.website_meta_title = False
            cleared += 1
        else:
            kept += 1
    _logger.info(
        "website_stockist: cleared %s generated stockist titles, kept %s "
        "hand-written ones; titles are now generated per website", cleared, kept)
