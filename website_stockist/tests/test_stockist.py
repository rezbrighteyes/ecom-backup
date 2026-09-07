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

    def test_range_appears_in_json_ld(self):
        import json
        tag = self.env["product.tag"].create({"name": "MJ59"})
        self.stockist.brand_ids = [(6, 0, [tag.id])]
        data = json.loads(self.stockist._json_ld("https://example.com").strip())
        offers = data["makesOffer"]
        self.assertEqual(offers[0]["itemOffered"]["name"], "MJ59")
        self.assertEqual(offers[0]["itemOffered"]["brand"]["name"], "Mangrove Jacks")

    def test_no_range_means_no_offer_block(self):
        import json
        data = json.loads(self.stockist._json_ld("https://example.com").strip())
        self.assertNotIn("makesOffer", data)
