# -*- coding: utf-8 -*-
"""Storefront menus: access, validation, the switch, the export shape, its
filtering rules, the content_version link and the gated endpoint."""

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from .. import catalogue, content, menu
from .common import TOKEN
from .test_content import ContentFixture

ITEM_KEYS = {"id", "name", "kind", "url", "new_window", "badge", "badge_style",
             "category_id", "children"}
CHILD_KEYS = {"id", "name", "url", "new_window", "badge", "badge_style"}
FEATURED_KEYS = {"id", "name", "slug"}
EXPORT_KEYS = {"contract", "generated_at", "website_id", "menu"}


class MenuFixture(ContentFixture):

    @classmethod
    def _setup_menu(cls):
        cls._setup_content()
        env = cls.env
        cls.Menu = env["website.menu"]
        cls.Featured = env["reza.storefront.featured.brand"]
        root = cls.website.menu_id
        if not root:
            root = cls.Menu.create({"name": "SF Top", "website_id": cls.website.id})
            cls.website.invalidate_recordset(["menu_id"])
        cls.root = cls.website.menu_id
        # Start from an empty menu (a new website copies Odoo's default one).
        cls.root.child_id.unlink()
        cls.brand_b = env["product.data.feed.brand"].create({"name": "Sf Second Brand"})
        cls.brand_empty = env["product.data.feed.brand"].create({"name": "Sf Empty Brand"})
        cls.make_template("SF Second Brand Glasses", feed_brand_id=cls.brand_b.id)

    def item(self, name, seq, parent=None, **vals):
        base = {"name": name, "url": "/shop", "sequence": seq, "website_id": self.website.id,
                "parent_id": (parent or self.root).id}
        base.update(vals)
        return self.Menu.create(base)

    def switch(self, on=True):
        self.website.rz_storefront_use_odoo_menu = on

    def site(self):
        return catalogue.public_site(self.website)

    def exported(self):
        return {row["id"]: row for row in menu.menu_payload(self.site())["items"]}


@tagged("post_install", "-at_install")
class TestMenu(MenuFixture, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_menu()

    # ------------------------------------------------------------ access

    def _check_field(self, model, name):
        if hasattr(model, "check_field_access"):  # 18/20: check_field_access on 20
            model.check_field_access(model._fields[name], "read")
        else:
            model.check_field_access_rights("read", [name])

    def test_featured_brand_model_is_designers_only(self):
        for user in (self.public, self.portal, self.staff):
            for operation in ("read", "write", "create", "unlink"):
                with self.assertRaises(AccessError, msg=(user.login, operation)):
                    self.Featured.with_user(user).check_access(operation)
        for operation in ("read", "write", "create", "unlink"):
            self.Featured.with_user(self.designer).check_access(operation)
        row = self.Featured.with_user(self.designer).create(
            {"website_id": self.website.id, "brand_id": self.brand.id})
        row.sequence = 3
        self.assertEqual(row.brand_id, self.brand)

    def test_website_menu_fields_are_not_public(self):
        Website = self.env["website"]
        for name in ("rz_storefront_use_odoo_menu", "rz_storefront_featured_brand_ids"):
            for user in (self.public, self.portal, self.staff):
                restricted = Website.with_user(user)
                self._check_field(restricted, "name")  # control: not a blanket refusal
                with self.assertRaises(AccessError, msg=(name, user.login)):
                    self._check_field(restricted, name)
            self._check_field(Website.with_user(self.designer), name)

    def test_only_designers_write_menu_items(self):
        entry = self.item("SF Sale", 1)
        with self.assertRaises(AccessError):
            entry.with_user(self.staff).write({"rz_badge": "Up to 75%"})
        entry.with_user(self.designer).write({"rz_badge": "Up to 75%"})
        self.assertEqual(entry.rz_badge, "Up to 75%")

    def test_menu_button_needs_website_designer(self):
        for user in (self.staff, self.portal):
            with self.assertRaises(AccessError, msg=user.login) as cm:
                self.website.with_user(user).action_rz_storefront_menu()
            self.assertIn("Only website designers", str(cm.exception))
        action = self.website.with_user(self.designer).action_rz_storefront_menu()
        self.assertEqual(action["res_model"], "website.menu")
        self.assertIn(("website_id", "=", self.website.id), action["domain"])
        self.assertEqual(action["context"]["default_parent_id"], self.root.id)

    # ------------------------------------------------------------ validation

    def test_badge_validation(self):
        self.item("SF ok", 1, rz_badge="x" * 24)
        with self.assertRaises(ValidationError) as cm:
            self.item("SF long", 2, rz_badge="x" * 25)
        self.assertIn("longer than 24", str(cm.exception))
        for bad in ("<b>75%</b>", "a\nb", "   "):
            with self.assertRaises(ValidationError, msg=repr(bad)) as cm:
                self.item("SF bad", 3, rz_badge=bad)
            self.assertIn("cannot show", str(cm.exception))

    def test_category_pairing(self):
        with self.assertRaises(ValidationError) as cm:
            self.item("SF cat", 1, rz_kind="category_mega")
        self.assertIn("needs its storefront category", str(cm.exception))
        with self.assertRaises(ValidationError) as cm:
            self.item("SF link", 2, rz_public_categ_id=self.category.id)
        self.assertIn("Only a category menu", str(cm.exception))
        self.item("SF cat", 3, rz_kind="category_mega", rz_public_categ_id=self.category.id)

    def test_featured_brand_is_unique_per_website(self):
        self.Featured.create({"website_id": self.website.id, "brand_id": self.brand.id})
        with self.assertRaises(ValidationError) as cm:
            self.Featured.create({"website_id": self.website.id, "brand_id": self.brand.id,
                                  "active": False})
        self.assertIn("already a featured brand", str(cm.exception))
        self.Featured.create({"website_id": self.other_website.id, "brand_id": self.brand.id})

    # ------------------------------------------------------------ switch

    def test_switch_off_exports_no_menu_and_keeps_the_version(self):
        self.item("SF Black Friday", 1, rz_badge="Up to 75%")
        self.Featured.create({"website_id": self.website.id, "brand_id": self.brand.id})
        site = self.site()
        self.assertFalse(self.website.rz_storefront_use_odoo_menu, "off by default")
        self.assertIsNone(menu.menu_payload(site))
        data = menu.export(site)
        self.assertEqual(set(data), EXPORT_KEYS)
        self.assertIsNone(data["menu"])
        # Off: exactly the blocks-only digest of the release before menus.
        payload = content.content_payload(site)
        self.assertEqual(content.content_version(site), content._version(payload["blocks"]))
        before = content.content_version(site)
        self.root.child_id[:1].name = "SF Renamed while off"
        self.assertEqual(content.content_version(site), before)

    def test_menu_edit_changes_content_version(self):
        entry = self.item("SF Black Friday", 1)
        site = self.site()
        off = content.content_version(site)
        self.switch()
        on = content.meta_fields(site)["content_version"]
        self.assertNotEqual(on, off, "turning the menu on is a content change")
        self.assertEqual(content.content_payload(site)["content_version"], on,
                         "the /content payload carries the same version as meta")
        entry.rz_badge = "Up to 75%"
        badged = content.content_version(site)
        self.assertNotEqual(badged, on)
        self.Featured.create({"website_id": self.website.id, "brand_id": self.brand.id})
        self.assertNotEqual(content.content_version(site), badged, "featured brands count")
        self.switch(False)
        self.assertEqual(content.content_version(site), off)

    # ------------------------------------------------------------ export

    def test_export_shape_and_order(self):
        self.switch()
        later = self.item("  SF   Collections ", 20, url="https://example.com/c",
                          new_window=True)
        sale = self.item("SF Black Friday", 10, url="/shop?order=list_price+asc",
                         rz_badge=" Up to 75% ", rz_badge_style="sale")
        cat = self.item("SF Sunnies", 30, rz_kind="category_mega",
                        rz_public_categ_id=self.category.id, url="#")
        brands = self.item("SF Brands", 5, rz_kind="brands_mega", url="#")
        drop = self.item("SF More", 40, rz_kind="drop", url="#")
        kid = self.item("SF Gift cards", 2, parent=drop, url="/gift", rz_badge="New",
                        rz_badge_style="new")
        self.Featured.create({"website_id": self.website.id, "brand_id": self.brand_b.id,
                              "sequence": 1})
        self.Featured.create({"website_id": self.website.id, "brand_id": self.brand.id,
                              "sequence": 2})
        section = menu.menu_payload(self.site())
        self.assertEqual(set(section), {"items", "featured_brands"})
        ids = [row["id"] for row in section["items"]]
        self.assertEqual(ids, [brands.id, sale.id, later.id, cat.id, drop.id])
        for row in section["items"]:
            self.assertEqual(set(row), ITEM_KEYS)
        rows = {row["id"]: row for row in section["items"]}
        self.assertEqual(rows[later.id]["name"], "SF Collections")
        self.assertTrue(rows[later.id]["new_window"])
        self.assertEqual((rows[sale.id]["badge"], rows[sale.id]["badge_style"]),
                         ("Up to 75%", "sale"))
        self.assertEqual(rows[sale.id]["url"], "/shop?order=list_price+asc")
        self.assertEqual((rows[cat.id]["kind"], rows[cat.id]["category_id"], rows[cat.id]["url"]),
                         ("category_mega", self.category.id, None))
        self.assertIsNone(rows[brands.id]["url"])
        self.assertIsNone(rows[drop.id]["url"], '"#" is not a storefront link')
        self.assertEqual(rows[drop.id]["children"], [{
            "id": kid.id, "name": "SF Gift cards", "url": "/gift", "new_window": False,
            "badge": "New", "badge_style": "new"}])
        self.assertEqual(set(rows[drop.id]["children"][0]), CHILD_KEYS)
        self.assertEqual([b["id"] for b in section["featured_brands"]],
                         [self.brand_b.id, self.brand.id])
        for row in section["featured_brands"]:
            self.assertEqual(set(row), FEATURED_KEYS)
        self.assertEqual(section["featured_brands"][1]["slug"], "sf-test-brand")

    def test_link_rule_drops_bad_links(self):
        self.switch()
        good = [self.item("SF path", 1, url="/about-us"),
                self.item("SF https", 2, url="https://example.com/x")]
        bad = [self.item("SF js", 3, url="javascript:alert(1)"),
               self.item("SF http", 4, url="http://example.com"),
               self.item("SF proto", 5, url="//evil.example"),
               self.item("SF hash", 6, url="#"),
               self.item("SF quote", 7, url='/shop"onmouseover=alert(1)'),
               self.item("SF mail", 8, url="mailto:a@example.com")]
        drop = self.item("SF drop", 9, rz_kind="drop")
        kid_ok = self.item("SF kid ok", 1, parent=drop, url="/kid")
        kid_bad = self.item("SF kid bad", 2, parent=drop, url="javascript:x")
        empty_drop = self.item("SF empty drop", 10, rz_kind="drop")
        self.item("SF only bad kid", 1, parent=empty_drop, url="http://example.com")
        rows = self.exported()
        for entry in good:
            self.assertIn(entry.id, rows, entry.url)
        for entry in bad:
            self.assertNotIn(entry.id, rows, entry.url)
        self.assertEqual([k["id"] for k in rows[drop.id]["children"]], [kid_ok.id])
        self.assertNotIn(kid_bad.id, [k["id"] for k in rows[drop.id]["children"]])
        self.assertNotIn(empty_drop.id, rows, "a short list needs a valid sub-menu")

    def test_hidden_and_group_menus_are_left_out(self):
        self.switch()
        shown = self.item("SF shown", 1)
        grouped = self.item("SF staff only", 2,
                            group_ids=[Command.set([self.env.ref("base.group_user").id])])
        for_public = self.item("SF visitors only", 5,
                               group_ids=[Command.set([self.env.ref("base.group_public").id])])
        view = self.env["ir.ui.view"].create({
            "name": "sf_hidden_page", "type": "qweb", "key": "reza_storefront_api.sf_hidden",
            "arch": '<t t-name="reza_storefront_api.sf_hidden"><div>x</div></t>'})
        page = self.env["website.page"].create({
            "url": "/sf-hidden-page", "view_id": view.id, "website_id": self.website.id,
            "is_published": False})
        unpublished = self.item("SF unpublished page", 3, url="/sf-hidden-page",
                                page_id=page.id)
        drop = self.item("SF drop", 4, rz_kind="drop")
        self.item("SF kid shown", 1, parent=drop, url="/k1")
        hidden_kid = self.item("SF kid grouped", 2, parent=drop, url="/k2",
                               group_ids=[Command.set([self.env.ref("base.group_user").id])])
        page_kid = self.item("SF kid unpublished page", 3, parent=drop, url="/sf-hidden-page",
                             page_id=page.id)
        rows = self.exported()
        self.assertIn(shown.id, rows)
        self.assertNotIn(grouped.id, rows)
        self.assertIn(for_public.id, rows, "a menu for the Public group is for visitors")
        self.assertNotIn(unpublished.id, rows)
        kids = [k["id"] for k in rows[drop.id]["children"]]
        self.assertNotIn(hidden_kid.id, kids)
        self.assertNotIn(page_kid.id, kids)
        page.is_published = True
        self.env.invalidate_all()  # is_visible is a plain compute, cached per transaction
        self.assertIn(unpublished.id, self.exported(), "control: a published page's menu shows")

    def test_category_and_brands_items(self):
        self.switch()
        own = self.item("SF cat", 1, rz_kind="category_mega", rz_public_categ_id=self.category.id)
        again = self.item("SF cat again", 2, rz_kind="category_mega",
                          rz_public_categ_id=self.category.id)
        foreign = self.item("SF foreign cat", 3, rz_kind="category_mega",
                            rz_public_categ_id=self.foreign_category.id)
        first = self.item("SF brands", 4, rz_kind="brands_mega")
        second = self.item("SF brands again", 5, rz_kind="brands_mega")
        rows = self.exported()
        self.assertIn(own.id, rows)
        self.assertNotIn(again.id, rows, "one panel per category")
        self.assertNotIn(foreign.id, rows, "a category of another website")
        self.assertIn(first.id, rows)
        self.assertNotIn(second.id, rows, "one Brands panel")

    def test_featured_brands_rules(self):
        self.switch()
        F = self.Featured
        F.create({"website_id": self.website.id, "brand_id": self.brand.id, "sequence": 5})
        F.create({"website_id": self.website.id, "brand_id": self.brand_empty.id, "sequence": 1})
        F.create({"website_id": self.website.id, "brand_id": self.brand_b.id, "sequence": 2,
                  "active": False})
        F.create({"website_id": self.other_website.id, "brand_id": self.brand_b.id})
        got = [b["id"] for b in menu.featured_brands(self.site())]
        self.assertEqual(got, [self.brand.id],
                         "no products, inactive and another website's rows are left out")

    def test_limits(self):
        self.switch()
        made = [self.item("SF item %02d" % i, i) for i in range(menu.MAX_ITEMS + 3)]
        self.item("SF " + "n" * menu.NAME_MAX, 0)
        rows = menu.menu_payload(self.site())["items"]
        self.assertEqual([r["id"] for r in rows], [m.id for m in made[:menu.MAX_ITEMS]])


@tagged("post_install", "-at_install")
class TestMenuHttp(MenuFixture, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_menu()
        cls.website.domain = cls.base_url()

    def _get(self, path, token=TOKEN):
        headers = {"X-Storefront-Token": token} if token else {}
        return self.opener.get(self.base_url() + path, headers=headers, allow_redirects=False,
                               timeout=60)

    def _assert_404(self, res, what):
        self.assertEqual(res.status_code, 404, what)
        self.assertEqual(res.json(), {"error": "not_found"}, what)

    def test_menu_endpoint_uses_the_same_gate(self):
        self.item("SF Black Friday", 1, rz_badge="Up to 75%")
        self._assert_404(self._get("/storefront/v1/menu", token=None), "no token")
        self._assert_404(self._get("/storefront/v1/menu", token="wrong" * 8), "bad token")
        self._assert_404(self._get("/storefront/v1/menu?x=1"), "unknown parameter")
        self._assert_404(self._get("/storefront/v1/menu/"), "trailing slash")
        res = self._get("/storefront/v1/menu")
        self.assertEqual(res.status_code, 200, res.text[:300])
        self.assertEqual(res.headers["Cache-Control"], "no-store")
        self.assertEqual(set(res.json()), EXPORT_KEYS)
        self.assertIsNone(res.json()["menu"], "switch off")
        self.assertNotIn("Black Friday", res.text)
        self.switch()
        body = self._get("/storefront/v1/menu").json()
        self.assertEqual([i["badge"] for i in body["menu"]["items"]], ["Up to 75%"])

    def test_anonymous_pages_render_with_storefront_menu_fields(self):
        """No session: the shop as a visitor sees it, with a badged, typed menu."""
        self.switch()
        self.item("SF Black Friday", 1, rz_badge="Up to 75%")
        self.item("SF cat", 2, rz_kind="category_mega", rz_public_categ_id=self.category.id)
        self.opener.cookies.clear()
        for path in ("/", "/shop"):
            res = self.opener.get(self.base_url() + path, allow_redirects=True, timeout=60)
            self.assertEqual(res.status_code, 200, path)
            self.assertIn("SF Black Friday", res.text, path)
