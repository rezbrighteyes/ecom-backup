# -*- coding: utf-8 -*-
"""Catalogue export, called directly (no HTTP). The HTTP boundary and pricing
equality against the real /website_sale/get_combination_info route are in
test_http.py."""

import json
import logging
from unittest.mock import patch

from odoo import Command, fields
from odoo.modules.neutralize import get_neutralization_queries
from odoo.tests import TransactionCase, tagged

from .. import catalogue
from .common import (
    ATTRIBUTE_KEYS, BANDS, BRAND_KEYS, CATEGORY_KEYS, IMAGE_KEYS, META_KEYS, ODOO_MAJOR,
    PAGE_KEYS, PRODUCT_KEYS, RATING_KEYS, RIBBON_KEYS, TOKEN, VALUE_KEYS, VARIANT_KEYS,
    WEBSITE_KEYS, CatalogueFixture,
)


@tagged("post_install", "-at_install")
class TestCatalogue(CatalogueFixture, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_catalogue()

    def _site(self):
        return catalogue.public_site(self.website)

    def _pricing(self):
        return catalogue.anonymous_pricing(self._site())

    def _all_pages(self, limit=200):
        site = self._site()
        page, rows, pages = 1, [], []
        while page:
            data = catalogue.products_page(site, page, limit, self._pricing())
            pages.append(data)
            rows.extend(data["products"])
            page = data["next_page"]
        return rows, pages

    def _row(self, template):
        rows = [p for p in self._all_pages(limit=500)[0] if p["id"] == template.id]
        self.assertEqual(len(rows), 1, "%s missing from the export" % template.name)
        return rows[0]

    # ------------------------------------------------------------ token

    def test_token_unset_closes_endpoint(self):
        self.params.search([("key", "=", catalogue.PARAM_TOKEN)]).unlink()
        for header in (None, "", " ", TOKEN, "False"):
            self.assertFalse(catalogue.token_ok(self.env, header), repr(header))

    def test_token_empty_parameter_closes_endpoint(self):
        for value in ("", "   ", " " * 40):
            self._set_token(value)
            for header in (None, "", value):
                self.assertFalse(catalogue.token_ok(self.env, header), repr((value, header)))

    def test_token_shorter_than_32_closes_endpoint(self):
        short = "a" * 31
        self._set_token(short)
        self.assertFalse(catalogue.token_ok(self.env, short))
        self._set_token("a" * 32)
        self.assertTrue(catalogue.token_ok(self.env, "a" * 32))

    def test_token_must_match_exactly(self):
        self.assertTrue(catalogue.token_ok(self.env, TOKEN))
        for header in (None, "", "wrong", TOKEN[:-1], TOKEN + "x", TOKEN.upper(), "éé"):
            self.assertFalse(catalogue.token_ok(self.env, header), repr(header))

    def test_neutralize_deletes_the_token(self):
        queries = list(get_neutralization_queries(["reza_storefront_api"]))
        self.assertTrue(queries, "data/neutralize.sql is missing")
        for query in queries:
            self.env.cr.execute(query)
        self.params.invalidate_model()
        self.assertFalse(self.params.search([("key", "=", catalogue.PARAM_TOKEN)]))

    # ------------------------------------------------------------ website / shop

    def test_website_resolved_from_exact_host_only(self):
        self.assertEqual(catalogue.website_for_host(self.env, "sf-test.example"), self.website)
        self.assertEqual(catalogue.website_for_host(self.env, "SF-TEST.example"), self.website)
        self.assertEqual(catalogue.website_for_host(self.env, "sf-test.example:443"), self.website)
        for host in ("", None, "unknown.example", "sf-test.example:8443", "evil.sf-test.example",
                     "sf-test.example/x", "sf-test.example?x", "sf-test.example#x",
                     "user@sf-test.example", "sf-test.example:99999", " sf-test.example x",
                     "sf-test.example\n", "//sf-test.example"):
            self.assertFalse(catalogue.website_for_host(self.env, host), repr(host))
        self.other_website.domain = "sf-test.example"  # two sites claim it: neither wins
        self.assertFalse(catalogue.website_for_host(self.env, "sf-test.example"))

    def test_website_user_must_be_public(self):
        self.assertIsNotNone(self._site())
        groups = "group_ids" if "group_ids" in self.env["res.users"]._fields else "groups_id"
        staff = self.env["res.users"].create({
            "name": "SF Site Staff", "login": "sf_site_staff",
            groups: [Command.set(self.env.ref("base.group_user").ids)],
        })
        for user in (staff, self.env.ref("base.user_root"), self.env["res.users"]):
            self.website.user_id = user
            self.assertIsNone(catalogue.public_site(self.website), user.login)

    def test_public_site_has_exactly_the_website_company(self):
        public = self.website.user_id
        public.write({"company_ids": [Command.link(self.other_company.id)]})
        site = self._site()
        self.assertEqual(site.env.companies, self.website.company_id)
        self.assertEqual(site.env.context.get("allowed_company_ids"), [self.website.company_id.id])

    def test_editor_flags_do_not_reach_the_export(self):
        flagged = self.website.with_context(edit_translations=True, editable=True,
                                            translatable=True)
        site = catalogue.public_site(flagged)
        for key in ("edit_translations", "editable", "translatable"):
            self.assertNotIn(key, site.env.context)

    def test_theme_holding_page_closes_the_shop(self):
        """YEO prelaunch (Odoo 18 yeo_website_theme) shows anonymous visitors a
        holding page; the export is closed while it is on."""
        Website = type(self.env["website"])
        with patch.object(Website, "_yeo_gate_on", lambda self_: True, create=True):
            self.assertFalse(catalogue.shop_open(self._site()))
        with patch.object(Website, "_yeo_gate_on", lambda self_: False, create=True):
            self.assertTrue(catalogue.shop_open(self._site()))

    def _gate_request(self, path, request_uri=None, **headers):
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request as WerkzeugRequest
        builder = EnvironBuilder(path=path, headers={
            "Host": "sf-test.example", "X-Storefront-Token": TOKEN, **headers})
        environ = builder.get_environ()
        environ["REQUEST_URI"] = request_uri or path

        class FakeRequest:
            pass

        fake = FakeRequest()
        fake.httprequest = WerkzeugRequest(environ)
        fake.env = self.env
        return fake

    def test_gate_uses_the_path_the_client_sent(self):
        """A rerouted request (language prefix, website rewrite) keeps the
        client's REQUEST_URI; the operation is chosen from that, not from a
        rewritten path or a parameter."""
        from .. import gate
        meta = "/storefront/v1/catalogue/meta"
        granted = gate.check(self._gate_request(meta))
        self.assertTrue(granted)
        self.assertEqual(granted[0], "meta")
        self.assertEqual(granted[1], self.website)
        for original in ("/en/storefront/v1/catalogue/meta", "/sf-alias-meta",
                         "/storefront/v1/catalogue"):
            self.assertIsNone(gate.check(self._gate_request(meta, request_uri=original)),
                              original)

    def test_login_only_shop_is_closed(self):
        self.assertTrue(catalogue.shop_open(self._site()))
        self.website.ecommerce_access = "logged_in"
        self.assertFalse(catalogue.shop_open(self._site()))

    # ------------------------------------------------------------ scope

    def test_scope_includes_and_excludes(self):
        rows, _pages = self._all_pages()
        ids = [r["id"] for r in rows]
        self.assertIn(self.pub.id, ids)
        self.assertIn(self.shared.id, ids, "a product with no website_ids is on every site")
        for template in self.excluded:
            self.assertNotIn(template.id, ids, "%s leaked into the export" % template.name)

    def test_scope_other_company_and_single_website_rule(self):
        ids = {r["id"] for r in self._all_pages()[0]}
        self.assertNotIn(self.other_company_product.id, ids,
                         "a product of an unrelated company leaked")
        self.assertNotIn(self.single_site_other.id, ids,
                         "a product whose website_id is another website leaked")
        meta = catalogue.meta(self._site())
        public_count = self._site().env["product.template"].search_count(
            catalogue.product_domain(self._site()))
        self.assertEqual(meta["product_count"], public_count)

    def test_selection_runs_as_public_user(self):
        templates = catalogue._public_templates(self._site())
        self.assertEqual(templates.env.user, self.website.user_id)
        self.assertFalse(templates.env.su)

    def test_paging_returns_every_product_once(self):
        rows, pages = self._all_pages(limit=1)
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), len(set(ids)), "a product appeared twice")
        site = self._site()
        expected = site.env["product.template"].search(
            catalogue.product_domain(site), order="id").ids
        self.assertEqual(ids, expected)
        self.assertEqual(pages[-1]["next_page"], None)
        self.assertEqual(pages[0]["product_count"], len(expected))

    def test_paging_limits(self):
        self.assertEqual(catalogue.parse_paging(None, None), (1, 200))
        self.assertEqual(catalogue.parse_paging("2", "9999"), (2, 500))
        self.assertEqual(catalogue.parse_paging("100000", "1"), (100000, 1))
        for bad in (("0", "10"), ("1", "0"), ("x", "10"), ("1", "-5"), ("100001", "1"),
                    ("1" * 100, "10"), (" 1", "10"), ("+1", "10"), ("1e3", "10"),
                    ("١", "10"), ("1\n", "10"), ("", "10"), ("1", "")):
            self.assertIsNone(catalogue.parse_paging(*bad), bad)

    def test_page_past_the_end_issues_no_offset_query(self):
        site = self._site()
        Template = type(site.env["product.template"])
        original = Template.search
        offsets = []

        def spy(records, domain, *args, **kwargs):
            offsets.append(kwargs.get("offset", 0))
            return original(records, domain, *args, **kwargs)

        with patch.object(Template, "search", spy):
            data = catalogue.products_page(site, 99999, 500, self._pricing())
        self.assertEqual(data["products"], [])
        self.assertIsNone(data["next_page"])
        self.assertFalse([o for o in offsets if o], "a search ran with a deep OFFSET")

    def test_page_with_too_many_variants_is_refused(self):
        site = self._site()
        ids = site.env["product.template"].search(
            catalogue.product_domain(site), order="id", limit=500).ids
        exact = self.env["product.product"].search_count([("product_tmpl_id", "in", ids)])
        with patch.object(catalogue, "MAX_VARIANTS_PER_PAGE", exact):
            catalogue.products_page(site, 1, 500, self._pricing())  # at the bound: served
        with patch.object(catalogue, "MAX_VARIANTS_PER_PAGE", exact - 1):
            with self.assertRaises(catalogue.PageTooLarge):
                catalogue.products_page(site, 1, 500, self._pricing())

    def test_variant_count_stops_at_the_bound(self):
        Product = type(self.env["product.product"])
        original = Product.search_count
        limits = []

        def spy(records, domain, *args, **kwargs):
            limits.append(kwargs.get("limit"))
            return original(records, domain, *args, **kwargs)

        with patch.object(Product, "search_count", spy):
            catalogue.products_page(self._site(), 1, 500, self._pricing())
        self.assertTrue(limits)
        self.assertTrue(all(lim == catalogue.MAX_VARIANTS_PER_PAGE + 1 for lim in limits), limits)

    def test_meta_is_bounded(self):
        site = self._site()
        with patch.object(catalogue, "MAX_META_ROWS", 0):
            with self.assertRaises(catalogue.PageTooLarge) as cm:
                catalogue.meta(site)
            self.assertEqual(cm.exception.what, "categories")
            # Brands alone, with the category bound out of the way:
            with patch.object(catalogue, "_public_categories",
                              lambda site_: site_.env["product.public.category"]):
                with self.assertRaises(catalogue.PageTooLarge) as cm:
                    catalogue.meta(site)
            self.assertEqual(cm.exception.what, "brands")

    # ------------------------------------------------------------ shape

    def test_field_allowlist(self):
        meta = catalogue.meta(self._site())
        self.assertEqual(set(meta), META_KEYS)
        self.assertEqual(set(meta["website"]), WEBSITE_KEYS)
        self.assertTrue(meta["categories"])
        for categ in meta["categories"]:
            self.assertEqual(set(categ), CATEGORY_KEYS)
        self.assertTrue(meta["brands"])
        for brand in meta["brands"]:
            self.assertEqual(set(brand), BRAND_KEYS)
        data = catalogue.products_page(self._site(), 1, 500, self._pricing())
        self.assertEqual(set(data), PAGE_KEYS)
        seen = {"ribbon": 0, "image": 0, "attribute": 0, "value": 0, "variant": 0}
        for row in self._all_pages(limit=500)[0]:
            self.assertEqual(set(row), PRODUCT_KEYS, row["id"])
            if row["ribbon"] is not None:
                self.assertEqual(set(row["ribbon"]), RIBBON_KEYS)
                seen["ribbon"] += 1
            if row["rating"] is not None:
                self.assertEqual(set(row["rating"]), RATING_KEYS)
            for image in row["images"]:
                self.assertEqual(set(image), IMAGE_KEYS)
                seen["image"] += 1
            for attr in row["attributes"]:
                self.assertEqual(set(attr), ATTRIBUTE_KEYS)
                seen["attribute"] += 1
                for value in attr["values"]:
                    self.assertEqual(set(value), VALUE_KEYS)
                    seen["value"] += 1
            for variant in row["variants"]:
                self.assertEqual(set(variant), VARIANT_KEYS)
                self.assertIn(variant["available_qty_band"], BANDS)
                seen["variant"] += 1
        for level, count in seen.items():
            self.assertGreater(count, 0, "no %s in the export to check" % level)

    def test_product_content(self):
        row = self._row(self.pub)
        self.assertEqual(row["name"], self.pub.name)
        self.assertEqual(row["url"], self.pub.website_url)
        self.assertEqual(row["brand_id"], self.brand.id)
        self.assertEqual(sorted(row["category_ids"]),
                         sorted((self.category | self.shared_child).ids),
                         "a category of another website must not be listed")
        self.assertEqual(row["meta_title"], "SF shared title")
        self.assertEqual(row["meta_keywords"], "sf, glasses")
        self.assertEqual(row["description_sale"], "SF sale text")
        self.assertEqual(row["ribbon"], {"name": "SF Sale", "bg": "#ff0000", "text": "#ffffff"})
        self.assertEqual(len(row["variants"]), 2)
        self.assertEqual(len(row["images"]), 1)
        self.assertRegex(row["images"][0]["url"],
                         r"^/web/image/product\.(template|image)/\d+/image_1920\?unique=\w{7}$")
        colour_values = {v["id"] for a in row["attributes"] for v in a["values"]}
        self.assertEqual(colour_values, set(self.colour.value_ids.ids))
        for variant in row["variants"]:
            record = self.env["product.product"].browse(variant["id"])
            self.assertEqual(variant["barcode"], record.barcode)
            self.assertTrue(set(variant["value_ids"]) <= colour_values)
            self.assertTrue(variant["url"].startswith(row["url"]), variant["url"])
        meta = catalogue.meta(self._site())
        self.assertIn(self.brand.id, [b["id"] for b in meta["brands"]])
        self.assertEqual(
            [b["slug"] for b in meta["brands"] if b["id"] == self.brand.id], ["sf-test-brand"])
        self.assertEqual(meta["website"]["id"], self.website.id)

    def test_hidden_attribute_is_not_exported(self):
        row = self._row(self.pub)
        self.assertNotIn(self.hidden_attr.id, [a["id"] for a in row["attributes"]])
        hidden_values = set(self.hidden_attr.value_ids.ids)
        for variant in row["variants"]:
            self.assertFalse(set(variant["value_ids"]) & hidden_values)
        # Nowhere in the row, URLs included: not the name, not its slug, not
        # the value id inside a URL.
        text = json.dumps(row).lower()
        for name in ("sf internal batch", "sf-internal-batch", "sf batch 7", "sf-batch-7"):
            self.assertNotIn(name, text)
        hidden_id = str(self.hidden_attr.value_ids.id)
        for variant in row["variants"]:
            tail = variant["url"][len(row["url"]):]
            tokens = tail.replace("=", ",").replace("&", ",").replace("-", ",").split(",")
            self.assertNotIn(hidden_id, tokens, variant["url"])

    def test_value_of_archived_variant_is_not_exported(self):
        row = self._row(self.sized)
        self.assertEqual(len(row["variants"]), 1)
        values = {v["id"] for a in row["attributes"] for v in a["values"]}
        self.assertNotIn(self.large_value.id, values)

    def test_categories_follow_public_visibility(self):
        site = self._site()
        meta = catalogue.meta(site)
        ids = [c["id"] for c in meta["categories"]]
        public_ids = site.env["product.public.category"].search(site.website_domain()).ids
        self.assertEqual(sorted(ids), sorted(public_ids))
        self.assertIn(self.category.id, ids)
        self.assertNotIn(self.foreign_category.id, ids)
        self.assertNotIn(self.foreign_parent.id, ids)
        if ODOO_MAJOR >= 19:
            # Odoo 20's public rule hides a category without published products.
            self.assertNotIn(self.empty_category.id, ids)
        child = next(c for c in meta["categories"] if c["id"] == self.shared_child.id)
        self.assertIsNone(child["parent_id"], "the other site's parent id leaked")
        self.assertIsNone(child["url"], "a URL built from the other site's parent leaked")

    def test_seo_override_per_website(self):
        self.pub.website_ids = [Command.link(self.other_website.id)]
        self.env["product.website.seo"].create({
            "product_tmpl_id": self.pub.id,
            "website_id": self.website.id,
            "meta_title": "SF override title",
        })
        self.env["product.website.seo"].create({
            "product_tmpl_id": self.pub.id,
            "website_id": self.other_website.id,
            "meta_description": "SF other-site description",
        })
        row = self._row(self.pub)
        self.assertEqual(row["meta_title"], "SF override title")
        self.assertNotEqual(row["meta_description"], "SF other-site description")

    def test_rating_needs_an_approval_decision(self):
        self.assertIsNone(self._row(self.pub)["rating"])
        Rating = self.env["rating.rating"].sudo()
        model_id = self.env["ir.model"]._get_id("product.template")
        vals = {"res_model_id": model_id, "res_id": self.pub.id, "rating": 4,
                "consumed": True, "partner_id": self.env.user.partner_id.id}
        approved = "is_approved" in Rating._fields
        Rating.create(dict(vals, **({"is_approved": True} if approved else {})))
        if approved:
            Rating.create(dict(vals, rating=1, is_approved=False))
        Rating.create(dict(vals, rating=1, consumed=False))
        self.pub.invalidate_recordset()
        expected = {"avg": 4.0, "count": 1} if approved else None
        self.assertEqual(self._row(self.pub)["rating"], expected,
                         "without reza_product_reviews there is no approval: rating must be null")

    def test_internal_reference_never_in_urls(self):
        # Odoo slugs a product from its display_name. On Odoo 18,
        # d3_product_reference adds the second reference to display_name, so
        # Odoo's own URL can carry it. Simulate that URL with default_code as
        # the internal reference, on both versions.
        self.shared.product_variant_id.default_code = "SFINTREF77"
        Template = type(self.env["product.template"])
        original = Template._compute_website_url

        def leaky(records):
            original(records)
            for record in records:
                if record.id == self.shared.id:
                    record.website_url = "/shop/sfintref77-sf-shared-glasses-%d" % record.id

        with patch.object(Template, "_compute_website_url", leaky), \
                patch.object(catalogue, "INTERNAL_REF_FIELDS", ("default_code",)):
            self.env.invalidate_all()
            self.assertIn("sfintref77", self.shared.website_url, "fixture: Odoo's URL leaks")
            row = self._row(self.shared)
        self.env.invalidate_all()
        for url in [row["url"]] + [v["url"] for v in row["variants"]]:
            self.assertNotIn("sfintref77", (url or "").lower(), url)
        self.assertTrue(row["url"].endswith("-%d" % self.shared.id), row["url"])
        # An seo_name typed with the reference: the URL falls back to the id.
        self.shared.seo_name = "sfintref77-glasses"
        with patch.object(Template, "_compute_website_url", leaky), \
                patch.object(catalogue, "INTERNAL_REF_FIELDS", ("default_code",)):
            self.env.invalidate_all()
            row = self._row(self.shared)
        self.env.invalidate_all()
        self.assertEqual(row["url"], "/shop/%d" % self.shared.id)

    # ------------------------------------------------------------ pricing

    def test_price_includes_default_no_variant_option(self):
        site = self._site()
        pricing = self._pricing()
        row = self._row(self.with_lens)
        template = catalogue._sudo_templates(site, self.with_lens.ids)
        variant = template.product_variant_id
        full = template._get_first_possible_combination(
            necessary_values=variant.product_template_attribute_value_ids)
        page_info = template._get_combination_info(
            combination=full, product_id=variant.id, add_qty=1.0,
            pricelist=pricing["pricelist"], fiscal_position=pricing["fiscal_position"])
        bare_info = template._get_combination_info(
            combination=variant.product_template_attribute_value_ids,
            product_id=variant.id, add_qty=1.0,
            pricelist=pricing["pricelist"], fiscal_position=pricing["fiscal_position"])
        self.assertNotEqual(page_info["price"], bare_info["price"], "fixture: surcharge applies")
        self.assertEqual(row["variants"][0]["price"], page_info["price"])
        self.assertEqual(row["price_min"], page_info["price"])

    def test_hidden_zero_price_has_no_price_and_no_strike(self):
        self.website.write({"prevent_sale": True, "prevent_sale_for": "zero_price"})  # 18/20
        zero = self.make_template("SF Free Glasses", list_price=0.0, compare_list_price=50.0)
        row = self._row(zero)
        self.assertIsNone(row["variants"][0]["price"])
        self.assertIsNone(row["variants"][0]["compare_price"])
        self.assertIsNone(row["price_min"])

    def test_members_only_pricelist_is_not_used(self):
        """The visitor's own pricelist selection (get_pricelist_available, with
        its overrides) decides; a members-only list removed there is never
        used, even when it would sort first (yeo_members on Odoo 18)."""
        group = self.env.ref("product.group_product_pricelist")
        self.env.ref("base.group_user").write({"implied_ids": [Command.link(group.id)]})
        members = self.env["product.pricelist"].create({
            "name": "SF Members", "website_id": self.website.id, "selectable": True,
            "sequence": 0, "company_id": self.website.company_id.id,
            "item_ids": [Command.create({
                "applied_on": "3_global", "compute_price": "fixed", "fixed_price": 3.0})]})
        self.env["product.pricelist"].create({
            "name": "SF Default", "website_id": self.website.id, "selectable": True,
            "sequence": 5, "company_id": self.website.company_id.id})
        Website = type(self.env["website"])
        original = Website.get_pricelist_available

        def without_members(self_, show_visible=False):
            return original(self_, show_visible=show_visible) - members

        with patch.object(Website, "get_pricelist_available", without_members):
            pricing = catalogue.anonymous_pricing(self._site())
            row = self._row(self.shared)
        self.assertNotEqual(pricing["pricelist"], members)
        self.assertNotEqual(row["variants"][0]["price"], 3.0)

    # ------------------------------------------------------------ stock

    def _stock(self, template, qty):
        variant = template.product_variant_id
        warehouse = self.website.warehouse_id or self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1)
        self.env["stock.quant"]._update_available_quantity(variant, warehouse.lot_stock_id, qty)
        self.env.invalidate_all()  # free_qty is a non-stored compute
        return variant

    def test_band_and_qty_follow_the_website_figure(self):
        self.shared.write({"allow_out_of_stock_order": False, "available_threshold": 5})
        variant = self.shared.product_variant_id
        self.assertEqual(self._row(self.shared)["variants"][0]["available_qty_band"], "out")
        self._stock(self.shared, 3)
        row = self._row(self.shared)["variants"][0]
        self.assertEqual(row["available_qty"], self.website._get_product_available_qty(variant))
        self.assertEqual(row["available_qty"], 3)
        self.assertEqual(row["available_qty_band"], "low")
        self._stock(self.shared, 20)
        self.assertEqual(self._row(self.shared)["variants"][0]["available_qty_band"], "in_stock")
        self.shared.allow_out_of_stock_order = True
        self._stock(self.shared, -23)
        self.assertEqual(self._row(self.shared)["variants"][0]["available_qty_band"], "in_stock")

    def test_available_qty_includes_edbert_rule(self):
        """reza_ecom_edbert_stock must be installed for this test to mean anything,
        so its absence is a failure, not a skip."""
        Product = self.env["product.product"]
        self.assertIn("reza_edbert_stock_state", Product._fields,
                      "reza_ecom_edbert_stock is not installed: the Edbert rule is untested")
        self.params.set_str("reza_ecom_edbert_stock.sell_buffer_qty", "1")  # 18/20
        self.params.set_str("reza_ecom_edbert_stock.sell_stale_hours", "3")
        self.params.set_str("reza_ecom_edbert_stock.last_sync", fields.Datetime.now())
        self.shared.allow_out_of_stock_order = False
        variant = self.shared.product_variant_id
        variant.sudo().write({"reza_edbert_free_qty": 12, "reza_edbert_stock_state": "ok"})
        expected = self.website._get_product_available_qty(variant)
        self.assertEqual(expected, 10, "12 at Edbert, less buffer 1, banded down to 10")
        row = self._row(self.shared)["variants"][0]
        self.assertEqual(row["available_qty"], expected)
        self.assertEqual(row["available_qty_band"], "in_stock")


@tagged("post_install", "-at_install")
class TestLogRedaction(TransactionCase):
    """Odoo 20 only: its HTTP server can log raw request headers."""

    SECRET = "sf-secret 'quoted' \"dq\" (paren), [br] =eq\\ 0123456789abcdef0123456789"

    def _request(self):
        import h11
        return h11.Request(method="GET", target="/storefront/v1/catalogue/meta", headers=[
            ("Host", "sf-test.example"), ("X-Storefront-Token", self.SECRET)])

    def _capture(self, call, keep_filters=True):
        from odoo.http import server_log
        records = []

        class Keep(logging.Handler):
            def emit(self, record):
                records.append(record)

        server_log.reset_thread_info()
        logger = logging.getLogger("odoo.http.server")
        headers_logger = logging.getLogger("odoo.http.server.headers")
        handler = Keep(level=logging.DEBUG)
        saved = (logger.level, headers_logger.level, logger.filters[:], logger.propagate)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        headers_logger.setLevel(logging.DEBUG)
        logger.propagate = False
        if not keep_filters:
            logger.filters = []
        try:
            call()
        finally:
            logger.removeHandler(handler)
            logger.setLevel(saved[0])
            headers_logger.setLevel(saved[1])
            logger.filters = saved[2]
            logger.propagate = saved[3]
        self.assertTrue(records, "fixture: nothing was logged")
        return records

    def _assert_clean(self, records):
        for record in records:
            dump = repr(record.__dict__) + record.getMessage()
            self.assertNotIn("0123456789abcdef0123456789", dump)
            self.assertNotIn("quoted", dump)
        self.assertIn("redacted", repr([r.__dict__ for r in records]))

    def test_secret_never_reaches_the_log_record(self):
        """The wrapped http_log redacts before Odoo builds any record: checked
        with the logging filter REMOVED, on the name the server module calls."""
        from odoo.http import server as http_server
        records = self._capture(
            lambda: http_server.http_log(logging.INFO, "", req=self._request(), res=None),
            keep_filters=False)
        self._assert_clean(records)

    def test_filter_redacts_text_and_header_attributes(self):
        """Second layer: a record that still carries the header (another code
        path) is redacted in its message, colored message and http_headers."""
        import pprint
        from .. import log_redaction
        headers = [(b"host", b"x"), (b"x-storefront-token", self.SECRET.encode())]
        record = logging.LogRecord("odoo.http.server", logging.DEBUG, __file__, 1,
                                   "req %s", ("X-Storefront-Token: " + self.SECRET,), None)
        record.msg = "GET /x\n" + pprint.pformat(headers) + " %s"
        record.colored_message = record.msg
        record.http_headers = headers
        log_redaction.RedactStorefrontToken().filter(record)
        self._assert_clean([record])
        self.assertTrue(any(isinstance(f, log_redaction.RedactStorefrontToken)
                            for f in logging.getLogger("odoo.http.server").filters))

    def _protocol_error(self):
        import h11
        conn = h11.Connection(h11.SERVER)
        conn.receive_data(b"GET / HTTP/1.1\r\nHost: x\r\nX-Storefront-Token : "
                          + self.SECRET.encode() + b"\r\n\r\n")
        try:
            conn.next_event()
        except h11.RemoteProtocolError as exc:
            return exc
        self.fail("fixture: h11 accepted the header line")

    def _formatted(self, records):
        fmt = logging.Formatter("%(message)s")
        return "\n".join(fmt.format(r) + repr(r.__dict__) for r in records)

    def test_protocol_error_traceback_never_carries_the_secret(self):
        """h11 quotes the bad header line in its exception; Odoo logs it with
        exc_info. Checked on the final formatted output, filter removed, with
        and without header DEBUG."""
        from odoo.http import server as http_server
        exc = self._protocol_error()
        self.assertIn("0123456789abcdef", str(exc), "fixture: h11 quotes the secret")

        def log():
            try:
                raise exc
            except Exception:  # noqa: BLE001
                http_server.http_log(logging.INFO, "", req=None, res=None, exc_info=True)

        for headers_debug in (True, False):
            records = self._capture(log, keep_filters=False)
            if not headers_debug:
                logging.getLogger("odoo.http.server.headers").setLevel(logging.WARNING)
            text = self._formatted(records)
            self.assertNotIn("0123456789abcdef", text)
            self.assertIn("RemoteProtocolError", text)

    def test_filter_redacts_a_logged_exception(self):
        from .. import log_redaction
        exc = self._protocol_error()
        record = logging.LogRecord("odoo.http.server", logging.INFO, __file__, 1, "x", None,
                                   (type(exc), exc, exc.__traceback__))
        log_redaction.RedactStorefrontToken().filter(record)
        self.assertNotIn("0123456789abcdef", self._formatted([record]))

    def test_redaction_keeps_the_rest_of_the_line(self):
        import pprint
        from .. import log_redaction
        long_secret = ("sf-secret 'q' " + "0123456789abcdef" * 12).encode()
        text = pprint.pformat([(b"host", b"x"), (b"x-storefront-token", long_secret)], width=60)
        self.assertGreater(text.count("b'"), 3, "fixture: pprint split the value")
        out = log_redaction.redact_text(text)
        self.assertNotIn("0123456789abcdef", out)
        self.assertIn("b'x'", out)
        access = '127.0.0.1 - "GET /storefront/v1/catalogue?x-storefront-token=a HTTP/1.1" 200 21'
        self.assertEqual(log_redaction.redact_text(access), access)
        self.assertEqual(log_redaction.redact_text("X-Storefront-Token: abc def\nHost: keep"),
                         "X-Storefront-Token: [redacted]\nHost: keep")
        self.assertEqual(
            log_redaction.redact_text("bad line: bytearray(b'X-Storefront-Token: abc') status=400"),
            "bad line: bytearray(b'X-Storefront-Token: [redacted]') status=400")
