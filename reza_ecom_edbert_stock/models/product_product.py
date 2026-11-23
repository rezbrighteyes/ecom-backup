# -*- coding: utf-8 -*-

from odoo import fields, models

EDBERT_STOCK_STATES = [
    ("never", "Not checked yet"),
    ("ok", "Matched"),
    ("no_match", "No Edbert product"),
    ("mismatch", "References disagree"),
    ("unverified", "Cannot be checked"),
]

# Every field below is limited to internal users on purpose.
#
# website_sale grants base.group_public and base.group_portal READ on both
# product.product and product.template (website_sale/security/ir.model.access.csv
# lines 2-7). A field with no groups= is therefore readable over call_kw by
# anyone who can register an account on the shop -- and these fields carry a
# supplier's stock position and its internal reference codes. No storefront
# template shows them, so the exposure would be silent.
#
# base.group_user is the right width rather than something narrower: the
# template figure is a STORED compute, and any internal user who edits a
# variant triggers its recompute. A narrower group would raise for them.
INTERNAL_ONLY = "base.group_user"


class ProductProduct(models.Model):
    _inherit = "product.product"

    reza_edbert_free_qty = fields.Float(
        string="Edbert Free Qty",
        digits="Product Unit of Measure",
        readonly=True,
        default=0.0,
        copy=False,
        groups=INTERNAL_ONLY,
        help="Free quantity Edbert holds at its own warehouse, excluding stock "
        "already reserved for other orders. A negative position is shown as "
        "zero, because none of it can be sold. Read from the wholesale "
        "database on a schedule. No ecom stock or valuation depends on it. "
        "The shop uses it (less a buffer, banded so the real figure is never "
        "shown) for products with 'Continue selling' off -- see "
        "models/website_stock.py.",
    )

    reza_edbert_stock_state = fields.Selection(
        selection=EDBERT_STOCK_STATES,
        string="Edbert Match",
        readonly=True,
        default="never",
        copy=False,
        groups=INTERNAL_ONLY,
        help="Whether this product could be matched to an Edbert product, and "
        "proved to be the same product.\n"
        "Matched: the figure beside it is real.\n"
        "No Edbert product: nothing to match, so no figure can be shown.\n"
        "References disagree: a product was found, but it carries neither this "
        "product's internal reference nor its barcode. The mapping is wrong, so "
        "the figure is withheld rather than shown for another product.\n"
        "Cannot be checked: this product carries no internal reference, so the "
        "mapping cannot be proved either way.",
    )

    reza_edbert_code = fields.Char(
        string="Edbert Reference",
        readonly=True,
        copy=False,
        groups=INTERNAL_ONLY,
        help="The internal reference the matched Edbert product carries. Filled "
        "in only when the match could not be proved, so a problem explains "
        "itself without a second lookup.",
    )

    reza_edbert_stock_date = fields.Datetime(
        string="Edbert Figure Changed",
        readonly=True,
        copy=False,
        groups=INTERNAL_ONLY,
        help="When this product's Edbert figure last changed. It is not the "
        "time of the last check: an unchanged figure is left alone, so that a "
        "check does not rewrite the whole catalogue.",
    )

    reza_edbert_last_sync = fields.Datetime(
        string="Edbert Last Checked",
        compute="_compute_reza_edbert_last_sync",
        groups=INTERNAL_ONLY,
        help="When the whole catalogue was last checked against Edbert.",
    )

    def _compute_reza_edbert_last_sync(self):
        value = self.env["reza.edbert.stock.sync"]._last_sync()
        for product in self:
            product.reza_edbert_last_sync = value
