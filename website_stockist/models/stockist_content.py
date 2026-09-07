"""What one stockist says on one website.

A shop that stocks two of the group's brands appears on two sites. The shop is
one thing — one address, one phone, one set of opening hours — but what it sells
and what it should say differ per brand. Publishing the same page on both
domains makes them compete, and the module's existing answer to that was
`canonical_website_id`: point the copies at one owner. Safe, but it means only
one site's stockist pages can ever rank.

This is the other answer. The stockist stays single, so the address is
maintained once and cannot drift between sites — address drift is one of the few
things that genuinely damages local search. Everything that should differ per
site moves onto a row here:

* **the stockist tag**, which is the important one. It selects the products, and
  the products drive the categories, the strip and the generated description. So
  a shop tagged for Rocko's on rockos.com.au and for Mangrove Jacks on
  mangrovejacks.net.au produces different copy on each site without anyone
  writing any.
* **the brand name** used in the sentence and in the Store JSON-LD. This was
  hardcoded to "Mangrove Jacks" and would have been wrong on every other site.
* optional overrides for the title, description and body when a store earns
  something bespoke.

Adding another website is adding a row, never another copy of this module.
"""
from odoo import api, fields, models


class WebsiteStockistContent(models.Model):
    _name = "website.stockist.content"
    _description = "Stockist content, per website"
    _order = "website_id, id"

    stockist_id = fields.Many2one(
        "website.stockist", required=True, ondelete="cascade", index=True)
    website_id = fields.Many2one(
        "website", required=True, ondelete="cascade", index=True,
        help="The site this content is for.")

    brand_name = fields.Char(
        string="Brand name",
        help="The brand as a customer would say it on this site — 'Mangrove "
             "Jacks', 'Rocko's'. Used in the description and as the brand in "
             "the page's Store JSON-LD. Falls back to the website's own name.",
    )
    stockist_tag_ids = fields.Many2many(
        "product.tag",
        "website_stockist_content_tag_rel",
        "content_id",
        "tag_id",
        string="Stockist tags",
        help="The tag naming this stockist on a product, for this site. Tag a "
             "product with it and this stockist may show it here. This is what "
             "makes the same shop read differently on two brands' websites.",
    )

    website_meta_title = fields.Char(string="Title override")
    website_meta_description = fields.Text(string="Description override")
    description = fields.Html(
        string="Body override", sanitize_attributes=False,
        help="Leave empty and the page uses the stockist's own body copy. Fill "
             "it only where a store deserves something specific on this site.",
    )

    _sql_constraints = [
        ("stockist_website_uniq",
         "unique(stockist_id, website_id)",
         "A stockist can only have one content row per website."),
    ]

    @api.depends("website_id", "brand_name")
    def _compute_display_name(self):
        for record in self:
            record.display_name = "%s — %s" % (
                record.stockist_id.name or "",
                record.brand_name or record.website_id.name or "")

    def _brand(self):
        """What to call the brand on this site. Never blank."""
        self.ensure_one()
        return (self.brand_name or self.website_id.name or "").strip()
