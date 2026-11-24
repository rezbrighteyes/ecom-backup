# -*- coding: utf-8 -*-
"""The endpoint over HTTP, as an anonymous visitor."""

from unittest.mock import patch
from urllib.parse import urlencode

from odoo import Command
from odoo.tests import HttpCase, tagged

from .common import TOKEN, CatalogueFixture

META = "/storefront/v1/catalogue/meta"
PRODUCTS = "/storefront/v1/catalogue"


@tagged("post_install", "-at_install")
class TestCatalogueHttp(CatalogueFixture, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_catalogue()
        # The test website is the one whose domain is the test server's host.
        cls.website.domain = cls.base_url()
        # A price the website must compute (tax added for display), so a raw
        # list_price in the export cannot pass for the website price.
        tax = cls.env["account.tax"].create({
            "name": "SF 15% excl", "amount": 15, "amount_type": "percent",
            "type_tax_use": "sale", "company_id": cls.env.company.id,
            "price_include_override": "tax_excluded",
        })
        cls.pub.taxes_id = [Command.set(tax.ids)]
        cls.website.show_line_subtotals_tax_selection = "tax_included"

    def _request(self, url, token=TOKEN, method="GET", headers=None, cookies=None, body=None,
                 files=None, **params):
        hdrs = dict(headers or {})
        if token is not None:
            hdrs["X-Storefront-Token"] = token
        if params:
            url = "%s?%s" % (url, urlencode(params))
        self._drop_cookie("session_id")
        for name, value in (cookies or {}).items():
            self.opener.cookies.set(name, value)
        try:
            full = url if url.startswith("http") else self.base_url() + url
            return self.opener.request(method, full, headers=hdrs, allow_redirects=False,
                                       timeout=60, data=body, files=files)
        finally:
            for name in (cookies or {}):
                self._drop_cookie(name)

    def _drop_cookie(self, name):
        for cookie in list(self.opener.cookies):
            if cookie.name == name:
                self.opener.cookies.clear(cookie.domain, cookie.path, cookie.name)

    def _get(self, url, token=TOKEN, **params):
        return self._request(url, token=token, **params)

    def _all_products(self, limit=500):
        page, rows = 1, []
        while page:
            res = self._get(PRODUCTS, page=page, limit=limit)
            self.assertEqual(res.status_code, 200, res.text[:300])
            data = res.json()
            rows.extend(data["products"])
            page = data["next_page"]
        return rows

    def _assert_refused(self, res, what):
        """Every refusal looks exactly like a missing route under the prefix."""
        baseline = self._get("/storefront/v1/no-such-endpoint", token=None)
        self.assertEqual(baseline.status_code, 404)
        self.assertEqual(res.status_code, 404, what)
        if res.request.method != "HEAD":
            self.assertEqual(res.text, baseline.text, what)
            self.assertNotIn("Traceback", res.text, what)
        self.assertEqual(res.headers.get("Content-Type"), baseline.headers.get("Content-Type"), what)
        self.assertEqual(res.headers.get("Cache-Control"), "no-store", what)
        self.assertNotIn("Allow", res.headers, what)
        self.assertNotIn("Set-Cookie", res.headers, what)
        self.assertNotIn("Location", res.headers, what)

    # ------------------------------------------------------------ refusals

    def test_404_without_or_with_wrong_token(self):
        for url in (META, PRODUCTS):
            for token in (None, "", "wrong", TOKEN + "x"):
                self._assert_refused(self._get(url, token=token), (url, token))

    def test_404_when_parameter_unset_or_short(self):
        self.env["ir.config_parameter"].sudo().search(
            [("key", "=", "reza_storefront_api.token")]).unlink()
        for url in (META, PRODUCTS):
            for token in (None, "", TOKEN, "False"):
                self._assert_refused(self._get(url, token=token), (url, token))
        self._set_token("short-token")
        self._assert_refused(self._get(META, token="short-token"), "short token")

    def test_404_for_other_methods_paths_and_aliases(self):
        for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            self._assert_refused(self._request(META, method=method), method)
        for url in (META + "/", PRODUCTS + "/", "/storefront", "/storefront/",
                    "/storefront/v1", "/storefront/v1/catalogue/meta/x"):
            self._assert_refused(self._get(url), url)

    def test_404_before_body_and_parameter_parsing(self):
        """Refused before Odoo parses a body or binds parameters: no framework
        413/500 and no upload processing, for any of these shapes."""
        self._assert_refused(self._request(META, method="POST",
                                           files={"f": ("a.txt", b"x" * 4096)}), "upload")
        self._assert_refused(self._request(META, body="a=1"), "GET with a body")
        for params in ({"self": "x"}, {"subpath": "v1/catalogue"}, {"foo": "1"},
                       {"page": "1", "foo": "1"}):
            self._assert_refused(self._get("%s?%s" % (PRODUCTS, urlencode(params))), params)
        self._assert_refused(self._get(META, page="1"), "meta takes no parameter")
        self._assert_refused(self._get(PRODUCTS + "?page=1&page=2"), "repeated parameter")

    def test_404_for_path_aliases(self):
        """Only the two paths as the client sent them: a language prefix in
        front of /storefront gets the same minimal JSON 404, not Odoo's
        language redirect or reroute."""
        for url in ("/en/storefront/v1/catalogue/meta", "/en_US/storefront/v1/catalogue/meta",
                    "/fr/storefront/v1/catalogue", "/en/storefront"):
            self._assert_refused(self._get(url), url)

    def test_refusal_sets_no_cookie_and_keeps_the_jar_usable(self):
        """A refused call must not hand out a session cookie: the build's next,
        valid call with the same cookie jar must still be served."""
        self._drop_cookie("session_id")
        full = self.base_url() + META
        refused = self.opener.request("GET", full, headers={}, allow_redirects=False, timeout=60)
        self.assertEqual(refused.status_code, 404)
        self.assertNotIn("Set-Cookie", refused.headers)
        self.assertFalse([c for c in self.opener.cookies if c.name == "session_id"])
        ok = self.opener.request("GET", full, headers={"X-Storefront-Token": TOKEN},
                                 allow_redirects=False, timeout=60)
        self.assertEqual(ok.status_code, 200, ok.text[:200])
        self.assertNotIn("Set-Cookie", ok.headers)

    def test_404_when_website_user_is_not_public(self):
        groups = "group_ids" if "group_ids" in self.env["res.users"]._fields else "groups_id"
        staff = self.env["res.users"].create({
            "name": "SF Site Staff", "login": "sf_site_staff_http",
            groups: [Command.set(self.env.ref("base.group_user").ids)],
        })
        self.website.user_id = staff
        self._assert_refused(self._get(META), "staff as website user")

    def test_404_while_theme_holding_page_is_on(self):
        with patch.object(type(self.env["website"]), "_yeo_gate_on", lambda self_: True,
                          create=True):
            self._assert_refused(self._get(META), "prelaunch")
            self._assert_refused(self._get(PRODUCTS), "prelaunch")

    def test_404_on_predispatch_failure_without_traceback(self):
        for token in (None, TOKEN):
            res = self._get(META, token=token, affiliate_id="x", debug="1")
            self._assert_refused(res, ("affiliate_id", token))

    def test_404_for_signed_in_caller_or_session_cookie(self):
        groups = "group_ids" if "group_ids" in self.env["res.users"]._fields else "groups_id"
        self.env["res.users"].create({
            "name": "SF Staff Http", "login": "sf_staff_http", "password": "sf_staff_http_pw1",
            groups: [(6, 0, [self.env.ref("base.group_user").id])],
        })
        self.authenticate("sf_staff_http", "sf_staff_http_pw1")
        sid = self.opener.cookies["session_id"]
        self._assert_refused(self._request(META, cookies={"session_id": sid}), "staff")
        self._assert_refused(self._request(META, cookies={"session_id": "anything"}), "cookie")

    def test_404_for_unknown_host(self):
        for host in ("unknown.example", "evil.example:80"):
            self._assert_refused(self._request(META, headers={"Host": host}), host)

    def test_404_for_login_only_shop(self):
        self.website.ecommerce_access = "logged_in"
        self._assert_refused(self._get(META), "login-only shop")
        self._assert_refused(self._get(PRODUCTS), "login-only shop")

    def test_bad_paging_is_a_plain_400(self):
        for params in ({"page": "x"}, {"page": "1" * 200}, {"page": "100001"}, {"limit": "-1"}):
            res = self._get(PRODUCTS, **params)
            self.assertEqual(res.status_code, 400, params)
            self.assertEqual(res.headers.get("Cache-Control"), "no-store")
            self.assertEqual(res.json(), {"error": "bad_paging"})

    # ------------------------------------------------------------ success

    def test_meta_and_two_pages(self):
        res = self._get(META)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Cache-Control"), "no-store")
        self.assertIn("application/json", res.headers.get("Content-Type"))
        self.assertNotIn("session_id", res.headers.get("Set-Cookie", ""))
        meta = res.json()
        self.assertEqual(meta["website"]["id"], self.website.id)
        self.assertGreaterEqual(meta["product_count"], 2)
        first = self._get(PRODUCTS, page=1, limit=1).json()
        second = self._get(PRODUCTS, page=2, limit=1).json()
        self.assertEqual(first["next_page"], 2)
        self.assertEqual(len(first["products"]), 1)
        self.assertEqual(len(second["products"]), 1)
        self.assertLess(first["products"][0]["id"], second["products"][0]["id"])

    def test_scope_over_http(self):
        ids = [p["id"] for p in self._all_products()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(self.pub.id, ids)
        self.assertIn(self.shared.id, ids)
        for template in self.excluded:
            self.assertNotIn(template.id, ids, template.name)

    def test_price_equals_combination_info(self):
        rows = {p["id"]: p for p in self._all_products()}
        row = rows[self.pub.id]
        self.assertEqual(len(row["variants"]), 2)
        for variant in row["variants"]:
            record = self.env["product.product"].browse(variant["id"])
            info = self.make_jsonrpc_request("/website_sale/get_combination_info", {
                "product_template_id": self.pub.id,
                "product_id": record.id,
                "combination": record.product_template_attribute_value_ids.ids,
                "add_qty": 1,
            })
            self.assertEqual(variant["price"], info["price"])
            self.assertAlmostEqual(variant["price"], 115.0, 2,
                                   msg="fixture: 100 + 15% tax shown tax-included")
            if info.get("has_discounted_price"):
                self.assertEqual(variant["compare_price"], info["list_price"])
            else:
                self.assertEqual(variant["compare_price"], info.get("compare_list_price"))
        self.assertEqual(row["price_min"], 115.0)
        # The no-variant option: the export equals the product page's default
        # combination (variant + first lens), not the bare variant.
        lens_row = rows[self.with_lens.id]
        variant = self.with_lens.product_variant_id
        info = self.make_jsonrpc_request("/website_sale/get_combination_info", {
            "product_template_id": self.with_lens.id,
            "product_id": variant.id,
            "combination": self.with_lens._get_first_possible_combination().ids,
            "add_qty": 1,
        })
        self.assertEqual(lens_row["variants"][0]["price"], info["price"])
        self.assertAlmostEqual(lens_row["variants"][0]["price"], 120.0, 2)

    def test_export_never_writes_a_cart(self):
        partner = self.website.user_id.partner_id
        pricelist = self.env["product.pricelist"].create({"name": "SF Cart PL"})
        order = self.env["sale.order"].create({
            "partner_id": partner.id, "website_id": self.website.id,
            "pricelist_id": pricelist.id,
            "order_line": [Command.create({"product_id": self.pub.product_variant_id.id})],
        })
        before = (order.pricelist_id.id, order.write_date, order.amount_total)
        self.assertEqual(self._get(META).status_code, 200)
        self.assertEqual(self._get(PRODUCTS).status_code, 200)
        order.invalidate_recordset()
        self.assertEqual((order.pricelist_id.id, order.write_date, order.amount_total), before)

    def _geo_setup(self):
        group = self.env.ref("product.group_product_pricelist")
        self.env.ref("base.group_user").write({"implied_ids": [Command.link(group.id)]})
        nz_group = self.env["res.country.group"].create({
            "name": "SF NZ", "country_ids": [Command.set(self.env.ref("base.nz").ids)]})
        self.env["product.pricelist"].create({
            "name": "SF Default", "website_id": self.website.id, "selectable": True,
            "sequence": 1, "company_id": self.website.company_id.id})
        self.env["product.pricelist"].create({
            "name": "SF NZ", "website_id": self.website.id, "selectable": True,
            "sequence": 2, "company_id": self.website.company_id.id,
            "country_group_ids": [Command.set(nz_group.ids)],
            "item_ids": [Command.create({
                "applied_on": "3_global", "compute_price": "fixed", "fixed_price": 7.0})]})

    def _from_nz(self):
        geoip_class = self._geoip_class()
        return patch.object(geoip_class, "country_code", property(
            lambda g: None if g.ip in ("", "0.0.0.0") else "NZ"))

    @staticmethod
    def _geoip_class():
        from odoo.http import geoip  # 18/20: odoo.http.GeoIP on 18
        return geoip.GeoIP

    def test_export_prices_ignore_the_callers_geoip(self):
        self._geo_setup()
        with self._from_nz():
            shop = self.make_jsonrpc_request("/website_sale/get_combination_info", {
                "product_template_id": self.shared.id,
                "product_id": self.shared.product_variant_id.id,
                "combination": [], "add_qty": 1})
            rows = {p["id"]: p for p in self._all_products()}
        self.assertEqual(shop["price"], 7.0, "fixture: a NZ visitor gets the NZ list")
        self.assertNotEqual(rows[self.shared.id]["variants"][0]["price"], 7.0,
                            "the export priced with the caller's GeoIP")

    def test_export_never_uses_session_pricing_or_cart(self):
        """The session-bound selectors (which can write a cart's pricelist) are
        never called by the export."""
        Website = type(self.env["website"])
        calls = []

        def forbid(name):
            def method(self_, *args, **kwargs):
                calls.append(name)
                raise AssertionError(name)
            return method

        names = ("_get_and_cache_current_pricelist", "_get_and_cache_current_cart",
                 "_get_and_cache_current_fiscal_position")  # 18/20
        patches = [patch.object(Website, name, forbid(name)) for name in names]
        for p_ in patches:
            p_.start()
        try:
            self.assertEqual(self._get(META).status_code, 200)
            self.assertEqual(self._get(PRODUCTS).status_code, 200)
        finally:
            for p_ in patches:
                p_.stop()
        self.assertEqual(calls, [])
