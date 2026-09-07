# -*- coding: utf-8 -*-
import json

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWebsiteStockist(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Stockist = cls.env["website.stockist"]
        cls.websites = cls.env["website"].search([], limit=2)
        cls.qld = cls.env["res.country.state"].search(
            [("country_id.code", "=", "AU"), ("code", "=", "QLD")], limit=1
        )

    def _make(self, **kw):
        vals = {"name": "Test Stockist", "is_published": True}
        vals.update(kw)
        return self.Stockist.create(vals)

    # ------------------------------------------------------------------
    def test_empty_website_ids_means_all_websites(self):
        """The convention borrowed from product.template must hold."""
        rec = self._make(website_ids=[(5, 0, 0)])
        self.assertFalse(rec.website_ids)
        for website in self.websites:
            domain = self.Stockist._get_published_domain(website.id)
            self.assertIn(
                rec, self.Stockist.search(domain),
                "A stockist with no website_ids must appear on every website.",
            )

    def test_website_ids_restricts(self):
        if len(self.websites) < 2:
            self.skipTest("needs at least two websites")
        first, second = self.websites[0], self.websites[1]
        rec = self._make(website_ids=[(6, 0, [first.id])])
        self.assertIn(rec, self.Stockist.search(
            self.Stockist._get_published_domain(first.id)))
        self.assertNotIn(rec, self.Stockist.search(
            self.Stockist._get_published_domain(second.id)))

    def test_unpublished_never_listed(self):
        rec = self._make(is_published=False)
        domain = self.Stockist._get_published_domain(self.websites[0].id)
        self.assertNotIn(rec, self.Stockist.search(domain))

    # ------------------------------------------------------------------
    def test_full_address_skips_missing_parts(self):
        rec = self._make(street="16 Torres Cres", city="North Lakes",
                         state_id=self.qld.id, zip="4509")
        self.assertEqual(rec.full_address, "16 Torres Cres, North Lakes, QLD, 4509")
        bare = self._make(name="No Address")
        self.assertEqual(bare.full_address or "", "",
                         "An address with no parts must be empty, not a run of commas.")

    def test_blank_store_code_becomes_null(self):
        """Two blank codes must not collide with the unique index."""
        a = self._make(name="A", store_code="")
        b = self._make(name="B", store_code="   ")
        self.assertFalse(a.store_code)
        self.assertFalse(b.store_code)

    # ------------------------------------------------------------------
    def test_json_ld_is_valid_and_omits_empty_address(self):
        rec = self._make(street="16 Torres Cres", city="North Lakes",
                         state_id=self.qld.id, zip="4509",
                         phone="(07) 3733 1220",
                         opening_hours="Mon-Fri: 9:00-17:30\n\nSat: 9:00-16:00\n")
        payload = json.loads(rec._json_ld("https://example.com/"))
        self.assertEqual(payload["@type"], "Store")
        self.assertEqual(payload["address"]["addressLocality"], "North Lakes")
        self.assertEqual(payload["openingHours"], ["Mon-Fri: 9:00-17:30", "Sat: 9:00-16:00"],
                         "Blank lines must not become empty openingHours entries.")

        bare = self._make(name="No Address JSON")
        payload = json.loads(bare._json_ld("https://example.com/"))
        self.assertNotIn("address", payload,
                         "An address node holding only @type must not be emitted.")

    def test_canonical_only_when_another_site_owns_it(self):
        if len(self.websites) < 2:
            self.skipTest("needs at least two websites")
        first, second = self.websites[0], self.websites[1]
        rec = self._make(canonical_website_id=first.id)
        self.assertFalse(rec._canonical_url(first),
                         "No canonical needed on the owning website.")
        if first.domain:
            self.assertTrue(rec._canonical_url(second))
        no_owner = self._make(name="No Owner")
        self.assertFalse(no_owner._canonical_url(second))

    def test_json_ld_survives_the_template_layer(self):
        """The block must reach the page as JSON, not as escaped entities.

        A plain str goes through QWeb's escaper and every double quote becomes
        an entity. Nothing decodes entities inside a script tag, so Google would
        receive text that is not JSON at all.
        """
        from markupsafe import Markup, escape

        rec = self._make(name='Smith & Sons "Optical" </script>')
        payload = rec._json_ld("https://example.com/")

        self.assertIsInstance(payload, Markup,
                              "A plain str would be escaped by t-out and stop being JSON.")
        self.assertEqual(escape(payload), payload,
                         "Escaping Markup must be a no-op; if it is not, the page breaks.")
        self.assertNotIn("</script>", payload,
                         "A closing script tag in the data must not close the block.")
        self.assertEqual(json.loads(payload)["name"], 'Smith & Sons "Optical" </script>',
                         "Escaping must survive a round trip unchanged.")

    def test_item_list_json_ld_is_markup(self):
        from markupsafe import Markup

        rec = self._make(name="List Member")
        payload = self.Stockist._item_list_json_ld(rec, "https://example.com/")
        self.assertIsInstance(payload, Markup)
        self.assertEqual(json.loads(payload)["numberOfItems"], 1)

    def test_website_url_is_stable(self):
        rec = self._make(name="Cairns Central")
        self.assertTrue(rec.website_url.startswith("/stockists/"))
        self.assertIn(str(rec.id), rec.website_url)


@tagged("post_install", "-at_install")
class TestGooglePlacesParsing(TransactionCase):
    """Pure parsers — no network, so these run anywhere."""

    def setUp(self):
        super().setUp()
        from odoo.addons.website_stockist.models import google_places
        self.gp = google_places
        self.payload = {
            "displayName": {"text": "BrightEyes Cairns Central"},
            "addressComponents": [
                {"longText": "GD-057", "shortText": "GD-057", "types": ["subpremise"]},
                {"longText": "1-21", "shortText": "1-21", "types": ["street_number"]},
                {"longText": "McLeod Street", "shortText": "McLeod St", "types": ["route"]},
                {"longText": "Cairns City", "shortText": "Cairns City", "types": ["locality"]},
                {"longText": "Queensland", "shortText": "QLD",
                 "types": ["administrative_area_level_1"]},
                {"longText": "4870", "shortText": "4870", "types": ["postal_code"]},
                {"longText": "Australia", "shortText": "AU", "types": ["country"]},
            ],
            "location": {"latitude": -16.9219, "longitude": 145.77},
            "nationalPhoneNumber": "(07) 4041 7341",
            "regularOpeningHours": {"weekdayDescriptions": [
                "Monday: 9:00 AM - 5:30 PM", "", "Sunday: Closed"]},
        }

    def test_subpremise_becomes_shop_number(self):
        """AU shopping-centre addresses carry the shop number in subpremise."""
        parsed = self.gp.parse_address_components(self.payload)
        self.assertEqual(parsed["street"], "GD-057/1-21 McLeod Street")
        self.assertEqual(parsed["city"], "Cairns City")
        self.assertEqual(parsed["state_code"], "QLD")

    def test_blank_weekday_lines_dropped(self):
        hours = self.gp.parse_opening_hours(self.payload)
        self.assertNotIn("", hours.split("\n"))

    def test_empty_payload_never_raises(self):
        self.assertEqual(self.gp.parse_location({}), (None, None))
        self.assertEqual(self.gp.parse_opening_hours({}), "")
        self.assertEqual(self.gp.parse_phone({}), "")
        parsed = self.gp.parse_address_components({})
        self.assertEqual(set(parsed.values()), {""})

    def test_locality_falls_back(self):
        parsed = self.gp.parse_address_components({"addressComponents": [
            {"longText": "Westcourt", "shortText": "Westcourt",
             "types": ["administrative_area_level_2"]}]})
        self.assertEqual(parsed["city"], "Westcourt")

    def test_untyped_street_component_still_yields_an_address(self):
        """Google sometimes ships the street line with no types at all.

        Stockland Rockhampton, 7 Sep 2026: addressComponents[0] was
        {"longText": "331 Yaamba Road"} with no "types" key, so a lookup by
        street_number and route found nothing and the sync offered a blank
        address — indistinguishable from a listing that has no street.
        """
        parsed = self.gp.parse_address_components({
            "formattedAddress": "Shop 96 Stockland Rockhampton, 331 Yaamba Road, "
                                "Norman Gardens QLD 4701, Australia",
            "addressComponents": [
                {"longText": "331 Yaamba Road", "languageCode": "en"},
                {"longText": "Norman Gardens", "shortText": "Norman Gardens",
                 "types": ["locality", "political"]},
                {"longText": "Queensland", "shortText": "QLD",
                 "types": ["administrative_area_level_1", "political"]},
                {"longText": "Australia", "shortText": "AU",
                 "types": ["country", "political"]},
                {"longText": "4701", "shortText": "4701", "types": ["postal_code"]},
            ],
        })
        # formattedAddress is preferred because it keeps the shop and centre.
        self.assertEqual(parsed["street"],
                         "Shop 96 Stockland Rockhampton, 331 Yaamba Road")
        self.assertEqual(parsed["city"], "Norman Gardens")
        self.assertEqual(parsed["zip"], "4701")

    def test_untyped_fallback_used_only_when_typed_parsing_fails(self):
        """A listing Google types properly must parse exactly as before."""
        parsed = self.gp.parse_address_components({
            "formattedAddress": "Shop 39/165 Morayfield Rd, Morayfield QLD 4506, Australia",
            "addressComponents": [
                {"longText": "39", "types": ["subpremise"]},
                {"longText": "165", "types": ["street_number"]},
                {"longText": "Morayfield Road", "types": ["route"]},
                {"longText": "Morayfield", "shortText": "Morayfield", "types": ["locality"]},
                {"longText": "Queensland", "shortText": "QLD",
                 "types": ["administrative_area_level_1"]},
                {"longText": "Australia", "shortText": "AU", "types": ["country"]},
                {"longText": "4506", "types": ["postal_code"]},
            ],
        })
        self.assertEqual(parsed["street"], "39/165 Morayfield Road")

    def test_untyped_components_after_the_suburb_are_not_glued_on(self):
        """Only untyped parts before the locality can be street."""
        street = self.gp._untyped_street({"addressComponents": [
            {"longText": "12 Somewhere Street"},
            {"longText": "Suburbia", "types": ["locality"]},
            {"longText": "junk after the suburb"},
        ]})
        self.assertEqual(street, "12 Somewhere Street")

    def test_formatted_fallback_refuses_to_guess(self):
        """No suburb in formattedAddress means no derived street."""
        self.assertEqual(
            self.gp._street_from_formatted(
                {"formattedAddress": "Somewhere entirely"}, city_hint="Nowhere"), "")
        self.assertEqual(self.gp._street_from_formatted({}, city_hint="X"), "")

    def test_suburb_inside_the_street_line_is_not_a_cut_point(self):
        """Stockland Hervey Bay's street contains its own suburb name."""
        self.assertEqual(
            self.gp._street_from_formatted(
                {"formattedAddress": "Stockland Hervey Bay Shopping Centre 6 Central "
                                     "Avenue Shop 63 Hervey Bay, Hervey Bay QLD 4655, "
                                     "Australia"},
                city_hint="Hervey Bay"),
            "Stockland Hervey Bay Shopping Centre 6 Central Avenue Shop 63 Hervey Bay")


class TestOpeningHoursSpecification(TransactionCase):
    """Google's weekdayDescriptions are prose and schema.org's are not."""

    def setUp(self):
        super().setUp()
        self.stockist = self.env["website.stockist"].create({
            "name": "Test Store",
            "opening_hours": "Monday: 9:00 AM – 5:30 PM\n"
                             "Thursday: 9:00 AM – 8:00 PM\n"
                             "Sunday: Closed",
        })

    def test_prose_hours_become_structured(self):
        spec = self.stockist._opening_hours_specification()
        self.assertEqual(len(spec), 3)
        self.assertEqual(spec[0], {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": "https://schema.org/Monday",
            "opens": "09:00", "closes": "17:30"})
        self.assertEqual(spec[1]["closes"], "20:00")

    def test_closed_day_has_no_times(self):
        """schema.org expresses a closed day as a day with no opens/closes."""
        spec = self.stockist._opening_hours_specification()
        self.assertEqual(spec[2], {
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": "https://schema.org/Sunday"})

    def test_unparseable_hours_fall_back_to_the_raw_text(self):
        """Never emit a half-parsed week; keep the prose rather than lie."""
        self.stockist.opening_hours = "Whenever we feel like it"
        self.assertEqual(self.stockist._opening_hours_specification(), [])
        import json
        data = json.loads(self.stockist._json_ld("https://example.com").strip())
        self.assertIn("openingHours", data)
        self.assertNotIn("openingHoursSpecification", data)

    def test_structured_hours_replace_the_prose_in_json_ld(self):
        import json
        data = json.loads(self.stockist._json_ld("https://example.com").strip())
        self.assertIn("openingHoursSpecification", data)
        self.assertNotIn("openingHours", data)


    def test_no_range_means_no_offer_block(self):
        import json
        data = json.loads(self.stockist._json_ld("https://example.com").strip())
        self.assertNotIn("makesOffer", data)

    def test_products_follow_the_ranges(self):
        """The product list is computed, not a snapshot taken at setup."""
        tag = self.env["product.tag"].create({"name": "MJ59"})
        product = self.env["product.template"].create({
            "name": "MJ59 Polarised", "product_tag_ids": [(6, 0, [tag.id])],
            "is_published": True})
        self.stockist.stockist_tag_ids = [(6, 0, [tag.id])]
        self.assertIn(product, self.stockist.product_ids)

    def test_unpublished_products_are_not_listed(self):
        """A stockist page must not advertise something with no page to link to."""
        tag = self.env["product.tag"].create({"name": "MJ89"})
        hidden = self.env["product.template"].create({
            "name": "MJ89 Draft", "product_tag_ids": [(6, 0, [tag.id])],
            "is_published": False})
        self.stockist.stockist_tag_ids = [(6, 0, [tag.id])]
        self.assertNotIn(hidden, self.stockist.product_ids)

    def test_no_ranges_means_no_products(self):
        self.stockist.stockist_tag_ids = [(5, 0, 0)]
        self.assertFalse(self.stockist.product_ids)

    def test_offers_name_products_not_ranges(self):
        """makesOffer must carry what a customer can buy, not an internal code."""
        import json
        tag = self.env["product.tag"].create({"name": "MJ49"})
        self.env["product.template"].create({
            "name": "MJ49 Wrap", "product_tag_ids": [(6, 0, [tag.id])],
            "is_published": True})
        self.stockist.stockist_tag_ids = [(6, 0, [tag.id])]
        data = json.loads(self.stockist._json_ld("https://example.com").strip())
        names = [o["itemOffered"]["name"] for o in data["makesOffer"]]
        self.assertIn("MJ49 Wrap", names)
        self.assertNotIn("MJ49", names)

    def test_archived_product_is_not_listed(self):
        """An archived product keeps its tags and must not come back."""
        tag = self.env["product.tag"].create({"name": "MJ39"})
        gone = self.env["product.template"].create({
            "name": "MJ39 Withdrawn", "product_tag_ids": [(6, 0, [tag.id])],
            "is_published": True})
        self.stockist.stockist_tag_ids = [(6, 0, [tag.id])]
        self.assertIn(gone, self.stockist.product_ids)
        gone.active = False
        self.stockist.invalidate_recordset(["product_ids"])
        self.assertNotIn(gone, self.stockist.product_ids)

    def test_non_sellable_product_is_not_listed(self):
        tag = self.env["product.tag"].create({"name": "MJFoot"})
        internal = self.env["product.template"].create({
            "name": "MJFoot Display Stand", "product_tag_ids": [(6, 0, [tag.id])],
            "is_published": True, "sale_ok": False})
        self.stockist.stockist_tag_ids = [(6, 0, [tag.id])]
        self.assertNotIn(internal, self.stockist.product_ids)

    def test_product_from_another_website_is_not_listed(self):
        """is_published is one boolean for the database, not one per site."""
        other = self.env["website"].create({"name": "Some Other Site"})
        mine = self.env["website"].create({"name": "This Site"})
        tag = self.env["product.tag"].create({"name": "MJ89"})
        theirs = self.env["product.template"].create({
            "name": "MJ89 Other Site Only", "product_tag_ids": [(6, 0, [tag.id])],
            "is_published": True, "website_id": other.id})
        shared = self.env["product.template"].create({
            "name": "MJ89 Everywhere", "product_tag_ids": [(6, 0, [tag.id])],
            "is_published": True, "website_id": False})
        self.stockist.website_ids = [(6, 0, [mine.id])]
        self.stockist.stockist_tag_ids = [(6, 0, [tag.id])]
        self.assertNotIn(theirs, self.stockist.product_ids)
        self.assertIn(shared, self.stockist.product_ids)

    def test_one_range_cannot_swamp_the_strip(self):
        """Products are taken from each range, not 24 from whichever sorts first."""
        big = self.env["product.tag"].create({"name": "Big"})
        small = self.env["product.tag"].create({"name": "Small"})
        for i in range(40):
            self.env["product.template"].create({
                "name": "AAA Big %02d" % i, "product_tag_ids": [(6, 0, [big.id])],
                "is_published": True})
        only = self.env["product.template"].create({
            "name": "ZZZ Small One", "product_tag_ids": [(6, 0, [small.id])],
            "is_published": True})
        self.stockist.stockist_tag_ids = [(6, 0, [big.id, small.id])]
        products = self.stockist.product_ids
        self.assertIn(only, products, "the thin range was crowded out")
        self.assertLessEqual(len(products), self.stockist.PRODUCT_DISPLAY_LIMIT)

    def test_a_thin_range_does_not_leave_the_strip_short(self):
        """Even sampling tops up rather than under-filling."""
        big = self.env["product.tag"].create({"name": "Big2"})
        small = self.env["product.tag"].create({"name": "Small2"})
        for i in range(40):
            self.env["product.template"].create({
                "name": "Big2 %02d" % i, "product_tag_ids": [(6, 0, [big.id])],
                "is_published": True})
        self.env["product.template"].create({
            "name": "Small2 only", "product_tag_ids": [(6, 0, [small.id])],
            "is_published": True})
        self.stockist.stockist_tag_ids = [(6, 0, [big.id, small.id])]
        self.assertEqual(len(self.stockist.product_ids),
                         self.stockist.PRODUCT_DISPLAY_LIMIT)

    def test_meta_names_only_the_categories_stocked(self):
        sun = self.env["product.tag"].create(
            {"name": "MJ49", "stockist_category": "sunglasses"})
        hat = self.env["product.tag"].create(
            {"name": "MJHat", "stockist_category": "headwear"})
        self.stockist.stockist_tag_ids = [(6, 0, [sun.id, hat.id])]
        self.stockist.city, self.stockist.zip = "Morayfield", "4506"
        description = self.stockist._meta_description()
        self.assertIn("sunglasses and headwear", description)
        self.assertNotIn("footwear", description)

    def test_meta_order_is_stable_not_tag_order(self):
        """Categories read in a fixed order however the tags were ticked."""
        foot = self.env["product.tag"].create(
            {"name": "MJPluggers", "stockist_category": "footwear"})
        sun = self.env["product.tag"].create(
            {"name": "MJ59", "stockist_category": "sunglasses"})
        self.stockist.stockist_tag_ids = [(6, 0, [foot.id, sun.id])]
        self.assertIn("sunglasses and footwear", self.stockist._meta_description())

    def test_unclassified_range_adds_no_word(self):
        """A tag nobody has categorised must not put a blank in the sentence."""
        plain = self.env["product.tag"].create({"name": "MJMystery"})
        self.stockist.stockist_tag_ids = [(6, 0, [plain.id])]
        description = self.stockist._meta_description()
        self.assertIn("Find Mangrove Jacks sunglasses at", description)
        self.assertNotIn("  ", description)

    def test_meta_never_exceeds_the_truncation_point(self):
        cats = ["sunglasses", "headwear", "footwear", "apparel", "accessories"]
        tags = [self.env["product.tag"].create({"name": "T%s" % c,
                                                "stockist_category": c}) for c in cats]
        self.stockist.write({
            "name": "A Very Long Retailer Name At A Large Shopping Centre",
            "city": "Somewhere With A Long Name", "zip": "4000",
            "phone": "(07) 1234 5678",
            "stockist_tag_ids": [(6, 0, [t.id for t in tags])]})
        self.assertLessEqual(len(self.stockist._meta_description()), 155)

    def test_phone_is_shortened_rather_than_dropped(self):
        """The number is the action; the sentence around it is not."""
        cats = ["sunglasses", "headwear", "footwear", "apparel"]
        tags = [self.env["product.tag"].create({"name": "P%s" % c,
                                                "stockist_category": c}) for c in cats]
        self.stockist.write({
            "name": "Anaconda Adventure HQ Chullora Superstore",
            "city": "Chullora", "zip": "2190", "phone": "(02) 9782 0276",
            "stockist_tag_ids": [(6, 0, [t.id for t in tags])]})
        description = self.stockist._meta_description()
        self.assertIn("(02) 9782 0276", description)
        self.assertLessEqual(len(description), 155)

    def test_page_shows_categories_not_tag_codes(self):
        """A customer knows "Sunglasses"; nobody knows what MJ39 is."""
        tags = [self.env["product.tag"].create(
            {"name": n, "stockist_category": "sunglasses"})
            for n in ("MJ39", "MJ49", "MJ59")]
        self.stockist.stockist_tag_ids = [(6, 0, [t.id for t in tags])]
        groups = self.stockist._category_groups()
        self.assertEqual([label for label, _ in groups], ["Sunglasses"])
        self.assertEqual(len(groups[0][1]), 3, "all three must be behind the one badge")

    def test_footwear_ranges_collapse_to_one_badge(self):
        pluggers = self.env["product.tag"].create(
            {"name": "MJPluggers", "stockist_category": "footwear"})
        nobbies = self.env["product.tag"].create(
            {"name": "MJNobbies", "stockist_category": "footwear"})
        sun = self.env["product.tag"].create(
            {"name": "MJ49", "stockist_category": "sunglasses"})
        self.stockist.stockist_tag_ids = [(6, 0, [pluggers.id, nobbies.id, sun.id])]
        labels = [label for label, _ in self.stockist._category_groups()]
        self.assertEqual(labels, ["Sunglasses", "Footwear"])

    def test_unclassified_range_is_not_shown_but_still_sells(self):
        """Publishing "MJMystery" to a customer is worse than publishing nothing."""
        mystery = self.env["product.tag"].create({"name": "MJMystery"})
        product = self.env["product.template"].create({
            "name": "Mystery Item", "product_tag_ids": [(6, 0, [mystery.id])],
            "is_published": True})
        self.stockist.stockist_tag_ids = [(6, 0, [mystery.id])]
        self.assertEqual(self.stockist._category_groups(), [])
        self.assertIn(product, self.stockist.product_ids)

    def test_one_retailer_tag_still_yields_every_category(self):
        """A stockist recorded with a single retailer tag, the Anaconda shape.

        The store carries one tag naming the retailer. That tag says nothing
        about the range — the products it is on do, through their own tags.
        """
        anaconda = self.env["product.tag"].create({"name": "Anaconda"})
        sun = self.env["product.tag"].create(
            {"name": "MJ49", "stockist_category": "sunglasses"})
        foot = self.env["product.tag"].create(
            {"name": "MJPluggers", "stockist_category": "footwear"})
        hat = self.env["product.tag"].create(
            {"name": "MJHat", "stockist_category": "headwear"})
        for name, other in (("Wrap", sun), ("Thong", foot), ("Cap", hat)):
            self.env["product.template"].create({
                "name": "MJ %s" % name,
                "product_tag_ids": [(6, 0, [anaconda.id, other.id])],
                "is_published": True})
        self.stockist.stockist_tag_ids = [(6, 0, [anaconda.id])]
        labels = [label for label, _ in self.stockist._category_groups()]
        self.assertEqual(labels, ["Sunglasses", "Headwear", "Footwear"])
        self.assertIn("sunglasses, headwear and footwear",
                      self.stockist._meta_description())

    def test_strip_spreads_across_categories_not_one_bucket(self):
        """24 products from one retailer tag must not all be sunglasses."""
        anaconda = self.env["product.tag"].create({"name": "Anaconda2"})
        sun = self.env["product.tag"].create(
            {"name": "MJ59x", "stockist_category": "sunglasses"})
        foot = self.env["product.tag"].create(
            {"name": "MJFootx", "stockist_category": "footwear"})
        for i in range(40):
            self.env["product.template"].create({
                "name": "AAA Sun %02d" % i, "is_published": True,
                "product_tag_ids": [(6, 0, [anaconda.id, sun.id])]})
        boot = self.env["product.template"].create({
            "name": "ZZZ Boot", "is_published": True,
            "product_tag_ids": [(6, 0, [anaconda.id, foot.id])]})
        self.stockist.stockist_tag_ids = [(6, 0, [anaconda.id])]
        self.assertIn(boot, self.stockist.product_ids,
                      "footwear was crowded out by the larger category")

    def test_categories_cover_all_stock_not_just_the_strip(self):
        """The strip is capped at 24; the badges describe everything stocked."""
        retailer = self.env["product.tag"].create({"name": "Anaconda3"})
        sun = self.env["product.tag"].create(
            {"name": "MJ69x", "stockist_category": "sunglasses"})
        rare = self.env["product.tag"].create(
            {"name": "MJShirtx", "stockist_category": "apparel"})
        for i in range(40):
            self.env["product.template"].create({
                "name": "Sun %02d" % i, "is_published": True,
                "product_tag_ids": [(6, 0, [retailer.id, sun.id])]})
        self.env["product.template"].create({
            "name": "zzz Shirt", "is_published": True,
            "product_tag_ids": [(6, 0, [retailer.id, rare.id])]})
        self.stockist.stockist_tag_ids = [(6, 0, [retailer.id])]
        self.assertIn("Apparel", [l for l, _ in self.stockist._category_groups()])

    def test_social_image_prefers_the_shopfront(self):
        import base64
        png = base64.b64encode(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        self.stockist.write({"image_1920": png, "logo": png})
        self.assertIn("/image_1920", self.stockist._social_image_url())

    def test_social_image_falls_back_to_the_logo(self):
        import base64
        png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        self.stockist.write({"image_1920": False, "logo": png})
        self.assertIn("/logo", self.stockist._social_image_url())

    def test_no_images_means_odoo_default_not_a_broken_url(self):
        """Falling through to the site logo is Odoo's job, not ours."""
        self.stockist.write({"image_1920": False, "logo": False})
        self.assertIsNone(self.stockist._social_image_url())

    def test_sitemap_entries_carry_a_lastmod(self):
        """lastmod is what Google reads to decide whether to recrawl."""
        from odoo.addons.website_stockist.controllers.main import _sitemap_stockists
        self.stockist.is_published = True
        entries = list(_sitemap_stockists(self.env, None, None))
        self.assertTrue(entries, "the sitemap callback yielded nothing")
        mine = [e for e in entries if e["loc"] == self.stockist.website_url]
        self.assertTrue(mine, "the published stockist is missing from the sitemap")
        self.assertIn("lastmod", mine[0])

    def test_unpublished_stockist_stays_out_of_the_sitemap(self):
        from odoo.addons.website_stockist.controllers.main import _sitemap_stockists
        self.stockist.is_published = False
        locs = [e["loc"] for e in _sitemap_stockists(self.env, None, None)]
        self.assertNotIn(self.stockist.website_url, locs)

    def test_a_stockist_tag_limits_a_store_to_its_own_range(self):
        """Two stockists, different tags, different stock — the BER/Anaconda shape.

        Stockists carry different parts of the range. Tagging the product with
        the stockist's own tag is what keeps each page honest about which part,
        and a product left untagged for a stockist never appears on its page.
        """
        ber = self.env["product.tag"].create({"name": "BERx"})
        anaconda = self.env["product.tag"].create({"name": "Anacondax"})
        sun = self.env["product.tag"].create(
            {"name": "MJ49y", "stockist_category": "sunglasses"})
        foot = self.env["product.tag"].create(
            {"name": "MJPluggersy", "stockist_category": "footwear"})

        both = self.env["product.template"].create({
            "name": "Sold everywhere", "is_published": True,
            "product_tag_ids": [(6, 0, [ber.id, anaconda.id, sun.id])]})
        ber_only = self.env["product.template"].create({
            "name": "BER exclusive", "is_published": True,
            "product_tag_ids": [(6, 0, [ber.id, foot.id])]})

        other = self.stockist.copy({"name": "Anaconda Somewhere"})
        self.stockist.stockist_tag_ids = [(6, 0, [ber.id])]
        other.stockist_tag_ids = [(6, 0, [anaconda.id])]

        self.assertIn(both, self.stockist.product_ids)
        self.assertIn(ber_only, self.stockist.product_ids)
        self.assertIn(both, other.product_ids)
        self.assertNotIn(ber_only, other.product_ids,
                         "a product not tagged for this stockist must not appear")

        # And the categories follow the stock, so only one of them claims footwear.
        self.assertIn("Footwear", [l for l, _ in self.stockist._category_groups()])
        self.assertNotIn("Footwear", [l for l, _ in other._category_groups()])

    def test_fishing_tackle_reads_as_its_own_category(self):
        """Tackle is not apparel and not an accessory; it needed its own word."""
        tackle = self.env["product.tag"].create(
            {"name": "Lures", "stockist_category": "fishing"})
        shirt = self.env["product.tag"].create(
            {"name": "Fishing Apparel", "stockist_category": "apparel"})
        retailer = self.env["product.tag"].create({"name": "BERz"})
        for name, other in (("Hard Body Minnow", tackle), ("Kids Fishing Shirt", shirt)):
            self.env["product.template"].create({
                "name": name, "is_published": True,
                "product_tag_ids": [(6, 0, [retailer.id, other.id])]})
        self.stockist.stockist_tag_ids = [(6, 0, [retailer.id])]
        labels = [l for l, _ in self.stockist._category_groups()]
        self.assertEqual(labels, ["Apparel", "Fishing tackle"])
        self.assertIn("apparel and fishing tackle", self.stockist._meta_description())
