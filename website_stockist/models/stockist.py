# -*- coding: utf-8 -*-
import json
import re
from urllib.parse import quote

from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class WebsiteStockist(models.Model):
    """A retailer that stocks the group's product, published on one or more websites."""

    _name = "website.stockist"
    _description = "Website Stockist"
    _inherit = ["website.seo.metadata", "website.published.mixin", "mail.thread"]
    _order = "state_id, city, name"

    # How many products a stockist page will list before it stops.
    PRODUCT_DISPLAY_LIMIT = 24

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name = fields.Char(required=True, tracking=True, index=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    store_code = fields.Char(
        tracking=True,
        help="Internal reference. For BrightEyes stores this is the Neto warehouse "
             "code, e.g. 101 for Cairns Earlville.",
    )
    ownership = fields.Selection(
        [
            ("corporate", "Corporate"),
            ("franchise", "Franchise"),
            ("independent", "Independent retailer"),
            ("online", "Online only"),
        ],
        default="independent",
        required=True,
        tracking=True,
        help="Franchise and independent stockists may not be under our control for "
             "listing edits. Recorded so nobody edits a listing they do not own.",
    )

    # ------------------------------------------------------------------
    # Website assignment — many2many, matching the product.template convention
    # ------------------------------------------------------------------
    website_ids = fields.Many2many(
        "website",
        "website_stockist_website_rel",
        "stockist_id",
        "website_id",
        string="Websites",
        tracking=True,
        help="Websites this stockist appears on. LEAVE EMPTY to publish on every "
             "website — the same meaning empty website_ids carries on products in "
             "this database.",
    )

    canonical_website_id = fields.Many2one(
        "website",
        string="Canonical website",
        tracking=True,
        help="When a stockist appears on several websites they all serve the same URL "
             "path, which is cross-domain duplicate content. Nominate the website that "
             "owns the page and the others will point a canonical link at it. Leave "
             "empty when the stockist is on a single website.",
    )

    # ------------------------------------------------------------------
    # Address / NAP
    # ------------------------------------------------------------------
    street = fields.Char(tracking=True)
    street2 = fields.Char(tracking=True)
    city = fields.Char(tracking=True, index=True)
    state_id = fields.Many2one("res.country.state", string="State", tracking=True, index=True)
    zip = fields.Char(string="Postcode", tracking=True)
    country_id = fields.Many2one(
        "res.country",
        string="Country",
        tracking=True,
        default=lambda self: self.env.ref("base.au", raise_if_not_found=False),
    )
    phone = fields.Char(tracking=True)
    email = fields.Char(tracking=True)
    stockist_url = fields.Char(
        string="Stockist website",
        tracking=True,
        help="The stockist's own site, or their store page. Rendered as an outbound link.",
    )

    # ------------------------------------------------------------------
    # Geo
    # ------------------------------------------------------------------
    partner_latitude = fields.Float(string="Latitude", digits=(10, 7))
    partner_longitude = fields.Float(string="Longitude", digits=(10, 7))
    google_place_id = fields.Char(
        string="Google Place ID",
        help="Places API identifier. Filled automatically the first time you fetch "
             "from Google. Note this is NOT the CID held in store-codes.csv — Google "
             "does not officially convert between the two, so the first fetch "
             "resolves it by searching on name and address.",
    )
    google_sync_date = fields.Datetime(
        string="Last Google sync",
        readonly=True,
        help="When the address was last pulled from Google Places. Google's terms "
             "allow caching place_id indefinitely but other Places content for 30 "
             "days, so a stale date on a third-party stockist is worth refreshing.",
    )

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------
    description = fields.Html(
        sanitize_attributes=False,
        help="Shown on the stockist's own page. Write something specific to this "
             "location — duplicated boilerplate across stockists is worth nothing.",
    )
    opening_hours = fields.Text(
        help="One line per day, e.g. 'Mon-Fri: 9:00-17:30'. Rendered verbatim and "
             "emitted as openingHours in the page's Store JSON-LD.",
    )
    image_1920 = fields.Image(
        string="Photo",
        max_width=1920,
        max_height=1920,
        help="A photograph of the shopfront or interior. Pulled from Google when the "
             "listing has one. This is not the place for a logo — use the Logo field, "
             "which renders small beside the name.",
    )
    logo = fields.Image(
        string="Logo",
        max_width=512,
        max_height=512,
        help="The stockist's brand mark. Rendered at a fixed small size beside the "
             "name, so a large upload is scaled down rather than filling the page.",
    )
    image_source = fields.Selection(
        [("manual", "Uploaded here"), ("google", "Google Business Profile")],
        string="Photo source",
        default="manual",
        help="Set to Google when the photo came from the listing, so a later sync "
             "knows it may replace it. A photo uploaded here is never overwritten.",
    )
    # The relation table and column names have never changed through two
    # renames — brand_ids, then stockist_tag_ids, now this. An m2m is stored by table
    # rather than by field name, so each rename carried every existing row
    # across with no migration.
    stockist_tag_ids = fields.Many2many(
        "product.tag",
        "website_stockist_product_tag_rel",
        "stockist_id",
        "tag_id",
        string="Stockist tags",
        help="The tag that names this stockist on a product — BER, Anaconda. "
             "Tag a product with it and this stockist may show that product; "
             "leave it off and the product never appears here. Stockists carry "
             "different parts of the range, and this is what keeps each page "
             "honest about which part.\n\n"
             "The categories shown to a customer are not read from this tag. "
             "They come from the products it selects, so the page can never "
             "claim a category the stock does not support.",
    )
    product_ids = fields.Many2many(
        "product.template",
        string="Products in those ranges",
        compute="_compute_product_ids",
        help="Every published product carrying one of the ranges above. Computed, "
             "never stored: the answer has to follow the catalogue rather than a "
             "snapshot of it taken when the stockist was created.",
    )

    # ------------------------------------------------------------------
    # Computed
    # ------------------------------------------------------------------
    full_address = fields.Char(compute="_compute_full_address", store=True)
    google_maps_url = fields.Char(compute="_compute_google_maps_url")

    _sql_constraints = [
        (
            "store_code_uniq",
            "unique(store_code)",
            "Two stockists cannot share a store code.",
        ),
    ]

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normalise_store_code(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._normalise_store_code(vals)
        return super().write(vals)

    @staticmethod
    def _normalise_store_code(vals):
        """Blank store codes must be NULL, not ''.

        Postgres treats every NULL as distinct in a UNIQUE index but treats '' as a
        real value, so without this two blank codes collide and the second save
        fails with a constraint error the user cannot interpret.
        """
        if "store_code" in vals and not (vals.get("store_code") or "").strip():
            vals["store_code"] = False

    # ------------------------------------------------------------------
    # Compute / constraints
    # ------------------------------------------------------------------
    CATEGORY_ORDER = ["sunglasses", "headwear", "footwear", "apparel", "accessories"]

    def _stock_domain(self):
        """Products this stockist carries: published, sellable, on its websites."""
        self.ensure_one()
        domain = [("product_tag_ids", "in", self.stockist_tag_ids.ids),
                  ("is_published", "=", True),
                  ("sale_ok", "=", True),
                  ("active", "=", True)]
        if self.website_ids:
            domain.append(("website_id", "in", [False] + self.website_ids.ids))
        return domain

    def _categories_stocked(self):
        """{category: tag recordset} for the stock this stockist actually holds.

        Derived from the PRODUCTS, not from the tags ticked on the stockist. A
        retailer may be recorded with a single tag naming the retailer — every
        product Anaconda carries tagged "Anaconda" — and that tag says nothing
        about what is in the range. The products do: each carries its own range
        tags, and those carry the category.

        This also keeps the page honest for a store recorded the other way. Tick
        MJ49 on a BrightEyes store and the categories still come from what those
        products are, so the badges can never claim a category the stock does not
        support.

        Deliberately not limited to the products shown in the strip: the strip is
        capped at 24 and the categories describe everything stocked.
        """
        self.ensure_one()
        if not self.stockist_tag_ids:
            return {}
        products = self.env["product.template"].search(self._stock_domain())
        by_category = {}
        for tag in products.product_tag_ids:
            if tag.stockist_category:
                by_category.setdefault(tag.stockist_category,
                                       self.env["product.tag"].browse())
                by_category[tag.stockist_category] |= tag
        return by_category

    def _category_groups(self):
        """[(label, tag recordset)] — the categories a customer would recognise.

        Nobody outside the business knows what MJ39 is; they know "Sunglasses".
        A category whose tags nobody has classified simply does not appear —
        its products still show in the strip, so nothing is lost from the page.
        Publishing "MJMystery" to a customer would be worse than publishing
        nothing, and the backend's "Needs a stockist category" filter is how you
        find them.
        """
        self.ensure_one()
        labels = dict(self.env["product.tag"]._fields["stockist_category"].selection)
        stocked = self._categories_stocked()
        return [(labels[c], stocked[c]) for c in self.CATEGORY_ORDER if c in stocked]

    def _stocked_categories(self):
        """Category words for the description, in a stable, readable order."""
        stocked = self._categories_stocked()
        labels = dict(self.env["product.tag"]._fields["stockist_category"].selection)
        return [labels[c].lower() for c in self.CATEGORY_ORDER if c in stocked]

    @staticmethod
    def _join_readable(words):
        """['a', 'b', 'c'] -> 'a, b and c'."""
        if not words:
            return ""
        if len(words) == 1:
            return words[0]
        return "%s and %s" % (", ".join(words[:-1]), words[-1])

    def _meta_description(self):
        """What this stockist sells, where it is, and how to check stock.

        Built from the ranges rather than written once, so a store that gets
        hats tagged next week starts saying so without anyone editing 126 pages.
        Capped at 155 characters, the point past which Google truncates.
        """
        self.ensure_one()
        what = self._join_readable(self._stocked_categories()) or "sunglasses"
        where = " ".join(p for p in [self.city, self.zip] if p)
        text = "Find Mangrove Jacks %s at %s" % (what, self.name)
        if where:
            text += ", %s" % where
        text += "."
        if self.phone:
            # The phone number is the action; the invitation around it is not.
            # A store carrying four categories has a long enough opening that
            # the full sentence will not fit, so shorten rather than drop it.
            for tail in (" Call %s to check what's in stock." % self.phone,
                         " Call %s." % self.phone):
                if len(text) + len(tail) <= 155:
                    text += tail
                    break
        return text[:155]

    def _default_website_meta(self):
        res = super()._default_website_meta()
        for stockist in self:
            description = stockist._meta_description()
            res["default_meta_description"] = description
            res["default_opengraph"]["og:description"] = description
            res["default_twitter"]["twitter:description"] = description
            # Without this every stockist shares one social image: the site
            # logo. A shopfront tells someone which shop the link is about, and
            # each stockist already has one where Google's listing had a photo.
            image = stockist._social_image_url()
            if image:
                res["default_opengraph"]["og:image"] = image
                res["default_twitter"]["twitter:image"] = image
        return res

    def _social_image_url(self):
        """Absolute URL of the best image to represent this stockist, or None.

        The shopfront first, the stockist's own logo second, and nothing third —
        falling through to the site logo is what Odoo already does, and doing it
        here would only duplicate that.
        """
        self.ensure_one()
        field = "image_1920" if self.image_1920 else ("logo" if self.logo else None)
        if not field:
            return None
        base = self.env["website"].get_current_website().get_base_url()
        return "%s/web/image/website.stockist/%s/%s" % (base.rstrip("/"), self.id, field)

    @api.depends("stockist_tag_ids", "website_ids")
    def _compute_product_ids(self):
        """A spread of what this stockist carries, capped at PRODUCT_DISPLAY_LIMIT.

        Sampled evenly across CATEGORIES rather than across the tags ticked on
        the stockist. That distinction is the whole point once a retailer is
        recorded with a single tag naming the retailer: sampling by tag would
        return one bucket, and 24 products ordered by the merchandiser's own
        sequence are all sunglasses, so a store that genuinely sells footwear
        and headwear would show none of it.

        Products with no classified category are still eligible — they just
        cannot be sampled by category, so they fill any remaining room at the
        end rather than being excluded from a page whose stock they are part of.
        """
        Product = self.env["product.template"]
        for stockist in self:
            if not stockist.stockist_tag_ids:
                stockist.product_ids = False
                continue

            base = stockist._stock_domain()
            categories = stockist._categories_stocked()
            picked = Product.browse()

            if categories:
                share = max(1, self.PRODUCT_DISPLAY_LIMIT // len(categories))
                for category in self.CATEGORY_ORDER:
                    tags = categories.get(category)
                    if not tags:
                        continue
                    picked |= Product.search(
                        base + [("product_tag_ids", "in", tags.ids)],
                        order="website_sequence, name", limit=share,
                    )

            # A thin category leaves room; unclassified stock has nowhere else
            # to appear. Both are handled by topping up from everything.
            if len(picked) < self.PRODUCT_DISPLAY_LIMIT:
                picked |= Product.search(
                    base + [("id", "not in", picked.ids)],
                    order="website_sequence, name",
                    limit=self.PRODUCT_DISPLAY_LIMIT - len(picked),
                )
            stockist.product_ids = picked

    @api.depends("street", "street2", "city", "state_id", "zip")
    def _compute_full_address(self):
        for rec in self:
            state = ""
            if rec.state_id:
                state = rec.state_id.code or rec.state_id.name or ""
            parts = [rec.street, rec.street2, rec.city, state, rec.zip]
            rec.full_address = ", ".join(p.strip() for p in parts if p and p.strip())

    @api.depends("google_place_id", "full_address", "name")
    def _compute_google_maps_url(self):
        for rec in self:
            if rec.google_place_id:
                rec.google_maps_url = (
                    "https://www.google.com/maps/search/?api=1&query=%s&query_place_id=%s"
                    % (self._quote(rec.name or ""), self._quote(rec.google_place_id))
                )
            elif rec.full_address:
                rec.google_maps_url = (
                    "https://www.google.com/maps/search/?api=1&query=%s"
                    % self._quote("%s %s" % (rec.name or "", rec.full_address))
                )
            else:
                rec.google_maps_url = False

    @staticmethod
    def _quote(value):
        return quote(value or "", safe="")

    @api.constrains("email")
    def _check_email(self):
        pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
        for rec in self:
            if rec.email and not pattern.match(rec.email.strip()):
                raise ValidationError(_("'%s' is not a valid email address.") % rec.email)

    @api.constrains("partner_latitude", "partner_longitude")
    def _check_coordinates(self):
        for rec in self:
            if rec.partner_latitude and not (-90.0 <= rec.partner_latitude <= 90.0):
                raise ValidationError(_("Latitude must be between -90 and 90."))
            if rec.partner_longitude and not (-180.0 <= rec.partner_longitude <= 180.0):
                raise ValidationError(_("Longitude must be between -180 and 180."))

    # ------------------------------------------------------------------
    # Website plumbing
    # ------------------------------------------------------------------
    def _stockist_slug(self):
        """Slug for one record, across Odoo minor versions.

        `ir.http._slug` is the 17.4+ API. Older minors only expose the helper in
        `odoo.addons.http_routing.models.ir_http`. Falling back keeps every
        stockist URL working instead of raising AttributeError on all of them.
        """
        self.ensure_one()
        IrHttp = self.env["ir.http"]
        if hasattr(IrHttp, "_slug"):
            return IrHttp._slug(self)
        from odoo.addons.http_routing.models.ir_http import slug  # noqa: PLC0415
        return slug(self)

    def _compute_website_url(self):
        """Public URL for each stockist. Overrides website.published.mixin."""
        super()._compute_website_url()
        for rec in self:
            rec.website_url = "/stockists/%s" % rec._stockist_slug()

    @api.model
    def _stockist_website_domain(self, website_id=False):
        """Records visible on a given website.

        Empty ``website_ids`` means every website — deliberately mirroring how an
        empty ``website_ids`` behaves on ``product.template`` in this database, so
        the two models never disagree about what "unassigned" means.
        """
        if not website_id:
            return []
        return ["|", ("website_ids", "=", False), ("website_ids", "in", [website_id])]

    def _get_published_domain(self, website_id=False):
        return [("is_published", "=", True)] + self._stockist_website_domain(website_id)

    # ------------------------------------------------------------------
    # Structured data
    # ------------------------------------------------------------------
    def _opening_hours_list(self):
        """opening_hours text -> list of non-empty trimmed lines."""
        self.ensure_one()
        if not self.opening_hours:
            return []
        return [line.strip() for line in self.opening_hours.splitlines() if line.strip()]

    _DAY_URIS = {
        "monday": "https://schema.org/Monday",
        "tuesday": "https://schema.org/Tuesday",
        "wednesday": "https://schema.org/Wednesday",
        "thursday": "https://schema.org/Thursday",
        "friday": "https://schema.org/Friday",
        "saturday": "https://schema.org/Saturday",
        "sunday": "https://schema.org/Sunday",
    }

    @staticmethod
    def _to_24h(text):
        """"9:00 AM" -> "09:00". Returns None if it is not a time at all."""
        import re
        match = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\s*$",
                         text.strip().lower())
        if not match:
            match = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", text.strip())
            if not match:
                return None
            hour, minute = int(match.group(1)), match.group(2)
            return "%02d:%s" % (hour, minute) if 0 <= hour <= 23 else None
        hour = int(match.group(1))
        minute = match.group(2) or "00"
        if hour == 12:
            hour = 0
        if match.group(3) == "p":
            hour += 12
        return "%02d:%s" % (hour, minute)

    def _opening_hours_specification(self):
        """Structured OpeningHoursSpecification, or [] if the text will not parse.

        Google Places returns weekdayDescriptions as prose — "Thursday: 9:00 AM -
        8:00 PM" — separated by an en dash and padded with U+202F narrow no-break
        spaces. Emitting that as schema.org openingHours produces a value nothing
        can read. A day marked closed is emitted with no opens/closes, which is
        how schema.org expresses a closed day.
        """
        import re
        spec = []
        for line in self._opening_hours_list():
            if ":" not in line:
                continue
            day_part, _, times = line.partition(":")
            day = self._DAY_URIS.get(day_part.strip().lower())
            if not day:
                return []
            # Normalise the whitespace and dashes Google uses.
            times = re.sub(r"[\u2009\u202f\u00a0]", " ", times)
            times = re.sub(r"[\u2013\u2014]", "-", times).strip()
            if re.match(r"(?i)^closed$", times):
                spec.append({"@type": "OpeningHoursSpecification", "dayOfWeek": day})
                continue
            parts = [p for p in times.split("-") if p.strip()]
            if len(parts) != 2:
                return []
            opens, closes = self._to_24h(parts[0]), self._to_24h(parts[1])
            if not opens or not closes:
                return []
            spec.append({
                "@type": "OpeningHoursSpecification",
                "dayOfWeek": day,
                "opens": opens,
                "closes": closes,
            })
        return spec

    @staticmethod
    def _json_ld_dump(data):
        """Serialise structured data for a <script type="application/ld+json"> block.

        Two things must be right here or the block is worth nothing:

        * The result must be Markup. A plain str goes through QWeb's escaper,
          which turns every double quote into an HTML entity. Script content is
          raw text in HTML, so nothing decodes those entities back, and what
          reaches Google is not valid JSON.
        * The three markup characters must become unicode escapes first. They
          are legal inside a JSON string, so a stockist whose name contained a
          closing script tag would otherwise end the tag and inject markup.
        """
        payload = json.dumps(data, ensure_ascii=False)
        payload = (payload.replace("<", "\\u003c")
                          .replace(">", "\\u003e")
                          .replace("&", "\\u0026"))
        return Markup(payload)

    def _json_ld(self, base_url):
        """Store JSON-LD for one stockist. Returns Markup, or False."""
        self.ensure_one()
        if not self.name:
            return False
        url = "%s%s" % (base_url.rstrip("/"), self.website_url)
        data = {
            "@context": "https://schema.org",
            "@type": "Store",
            "@id": "%s#stockist" % url,
            "name": self.name,
            "url": url,
        }
        address = {"@type": "PostalAddress"}
        if self.street:
            address["streetAddress"] = ", ".join(
                p for p in [self.street, self.street2] if p
            )
        if self.city:
            address["addressLocality"] = self.city
        if self.state_id:
            address["addressRegion"] = self.state_id.code or self.state_id.name
        if self.zip:
            address["postalCode"] = self.zip
        if self.country_id:
            address["addressCountry"] = self.country_id.code
        # Only emit an address node if it carries something beyond its @type.
        if len(address) > 1:
            data["address"] = address
        if self.phone:
            data["telephone"] = self.phone
        if self.email:
            data["email"] = self.email
        if self.partner_latitude and self.partner_longitude:
            data["geo"] = {
                "@type": "GeoCoordinates",
                "latitude": self.partner_latitude,
                "longitude": self.partner_longitude,
            }
        hours = self._opening_hours_list()
        if hours:
            # Schema.org openingHours wants "Mo-Fr 09:00-17:30", not the human
            # line Google Places hands us ("Monday: 9:00 AM - 5:30 PM", with
            # narrow no-break spaces and an en dash). The raw line is not
            # parseable and was being emitted verbatim on every stockist.
            spec = self._opening_hours_specification()
            if spec:
                data["openingHoursSpecification"] = spec
            else:
                data["openingHours"] = hours
        if self.stockist_url:
            data["sameAs"] = [self.stockist_url]
        if self.image_1920:
            data["image"] = "%s/web/image/website.stockist/%s/image_1920" % (
                base_url.rstrip("/"), self.id,
            )
        if self.logo:
            # Google reads logo separately from image; a shopfront photo in the
            # logo slot is worse than no logo at all.
            data["logo"] = "%s/web/image/website.stockist/%s/logo" % (
                base_url.rstrip("/"), self.id,
            )
        if self.product_ids:
            # The range is the only thing this page holds that the retailer's own
            # store page does not. On the page it is a row of badges; without
            # this it is invisible to anything parsing the document, which is the
            # entire reason the directory exists.
            data["makesOffer"] = [{
                "@type": "Offer",
                "itemOffered": {
                    "@type": "Product",
                    "name": product.name,
                    "brand": {"@type": "Brand", "name": "Mangrove Jacks"},
                    "url": "%s%s" % (base_url.rstrip("/"), product.website_url),
                },
                "availableAtOrFrom": {"@id": data["@id"]},
            } for product in self.product_ids]
        if self.google_maps_url:
            data["hasMap"] = self.google_maps_url
        return self._json_ld_dump(data)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_geolocate(self):
        """Fill latitude/longitude from the address using base_geolocalize."""
        Geo = self.env["base.geocoder"]
        for rec in self:
            if not rec.full_address:
                continue
            result = Geo.geo_find(
                "%s, %s" % (rec.full_address, rec.country_id.name or ""),
                force_country=rec.country_id.name or None,
            )
            if result:
                rec.partner_latitude, rec.partner_longitude = result
        return True

    def action_fetch_from_google(self):
        """Open the diff wizard. Deliberately writes nothing by itself."""
        self.ensure_one()
        wizard = self.env["website.stockist.google.sync"].build_for_stockist(self)
        return {
            "type": "ir.actions.act_window",
            "name": _("Sync from Google"),
            "res_model": "website.stockist.google.sync",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_open_website(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": self.website_url,
            "target": "new",
        }

    @api.model
    def _item_list_json_ld(self, stockists, base_url, name="Stockists"):
        """ItemList JSON-LD for a page of stockists.

        Built here rather than in QWeb: templates have no `json` in scope, and
        hand-concatenating JSON in a template is how you ship invalid markup.
        """
        root = base_url.rstrip("/")
        items = []
        for index, rec in enumerate(stockists, start=1):
            items.append({
                "@type": "ListItem",
                "position": index,
                "url": "%s%s" % (root, rec.website_url),
                "name": rec.name,
            })
        if not items:
            return False
        return self._json_ld_dump({
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": name,
            "numberOfItems": len(items),
            "itemListElement": items,
        })

    def _canonical_url(self, current_website):
        """Absolute canonical URL when another website owns this page, else False.

        Returns False when there is nothing to say — same website, no canonical
        nominated, or the canonical site has no domain configured. Emitting a
        canonical that points at a domain-less website would be worse than none.
        """
        self.ensure_one()
        target = self.canonical_website_id
        if not target or not current_website or target.id == current_website.id:
            return False
        domain = (target.domain or "").strip().rstrip("/")
        if not domain:
            return False
        if not domain.startswith("http"):
            domain = "https://%s" % domain
        return "%s%s" % (domain, self.website_url)
