"""Which category a range belongs to, for the stockist meta description.

A stockist page should say what a customer can buy there — "sunglasses, hats and
footwear", not "MJ39, MJHat, MJPluggers". Mapping tag names to category words in
code would be wrong within a week: new ranges arrive and the mapping would not
know about them, so the page would quietly stop mentioning a category that is
genuinely stocked.

So the category lives on the tag. Classify a range once, and every stockist
carrying it describes itself correctly from then on.
"""
from odoo import api, fields, models

# Only used to seed the field on install, never consulted afterwards. A tag whose
# name does not match is left blank for a human to classify.
NAME_HINTS = (
    ("sunglasses", ("mjsun", "mj39", "mj49", "mj59", "mj69", "mj79", "mj89", "mj99")),
    ("footwear", ("mjfoot", "mjpluggers", "mjfishshoe", "mjnobbies")),
    ("headwear", ("mjhat", "hats", "caps", "beanie", "visor")),
    ("apparel", ("mjshirt",)),
)


class ProductTag(models.Model):
    _inherit = "product.tag"

    stockist_category = fields.Selection(
        [
            ("sunglasses", "Sunglasses"),
            ("footwear", "Footwear"),
            ("headwear", "Headwear"),
            ("apparel", "Apparel"),
            ("accessories", "Accessories"),
        ],
        string="Stockist category",
        help="What a customer would call this range. Used to describe a stockist "
             "in its meta description — a store carrying MJ49 and MJPluggers "
             "reads as 'sunglasses and footwear'. Leave blank and the range still "
             "shows on the page; it just does not add a word to the description.",
    )

    @api.model
    def _seed_stockist_categories(self):
        """Classify the ranges that exist today. Runs once, on install."""
        for category, prefixes in NAME_HINTS:
            tags = self.search([("stockist_category", "=", False)])
            match = tags.filtered(lambda t: t.name and t.name.strip().lower() in prefixes)
            if match:
                match.stockist_category = category
