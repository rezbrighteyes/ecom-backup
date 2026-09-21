from odoo import api, fields, models


class ProductWebsiteSeo(models.Model):
    """Per-website overrides for a product's storefront copy.

    Odoo scopes product content by language and never by website. One
    ``website_meta_title`` and one ``description_ecommerce`` serve every storefront
    carrying the product, and 785 of the 1,704 live products in this database are
    carried by two or more. A brand site and a multi-brand retailer sell the same
    stock to people searching completely differently, and until now they had to
    share a sentence.

    **A row is an exception, never a requirement.** Absent, the shared field is used
    exactly as before. Nothing has to be populated for the catalogue to keep working,
    because 785 products times four fields is 3,140 edits nobody is going to make.
    """

    _name = 'product.website.seo'
    _description = 'Per-website product SEO override'
    _order = 'product_tmpl_id, website_id'

    product_tmpl_id = fields.Many2one(
        'product.template', required=True, ondelete='cascade', index=True)
    website_id = fields.Many2one('website', required=True, ondelete='cascade')

    meta_title = fields.Char(
        translate=True,
        help="Overrides the shared meta title on this website only. Leave empty unless the "
             "product genuinely needs different words here -- the site name is added "
             "automatically by the website's own SEO Title Suffix and does not belong in this "
             "field.")
    meta_description = fields.Text(
        translate=True,
        help="Overrides the shared meta description on this website only.")
    description_ecommerce = fields.Html(
        translate=True, sanitize_attributes=False,
        help="Overrides the product page body copy on this website only.")
    _sql_constraints = [
        ('product_website_uniq', 'unique (product_tmpl_id, website_id)',
         'A product can have only one override row per website.'),
    ]

    @api.constrains('product_tmpl_id', 'website_id')
    def _check_website_carries_product(self):
        """A row for a site that does not show the product is a row nobody will ever see.

        It will also be silently wrong by the time anyone notices, which is worse than absent.
        An empty ``website_ids`` means all websites, matching the convention this database
        already uses on ``product.template`` and in ``website_stockist``.
        """
        for record in self:
            carried = record.product_tmpl_id.website_ids
            if carried and record.website_id not in carried:
                raise models.ValidationError(
                    "%s is not published on %s, so an override for that site would never be "
                    "used." % (record.product_tmpl_id.display_name, record.website_id.name))
