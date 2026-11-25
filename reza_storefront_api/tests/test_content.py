# -*- coding: utf-8 -*-
"""Storefront content blocks: access, validation, live window, export, the
media route, the refresh button and the "last published" status."""

import io
from datetime import timedelta
from unittest.mock import patch

from PIL import Image

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, TransactionCase, tagged

from .. import access, catalogue, content
from ..models import storefront_block
from .common import TOKEN, CatalogueFixture, blob, png
from .jwt_tools import AUD, TEAM

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 200


def raw_png(width=4, height=4):
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


class ContentFixture(CatalogueFixture):

    @classmethod
    def _setup_content(cls):
        cls._setup_catalogue()
        env = cls.env
        cls.Block = env["reza.storefront.block"]
        groups = "group_ids" if "group_ids" in env["res.users"]._fields else "groups_id"

        def user(login, *xmlids):
            return env["res.users"].with_context(no_reset_password=True).create({
                "name": login, "login": login,
                groups: [Command.set([env.ref(x).id for x in xmlids])],
            })

        cls.designer = user("sf_designer", "base.group_user", "website.group_website_designer")
        cls.staff = user("sf_staff", "base.group_user")
        cls.portal = user("sf_portal", "base.group_portal")
        cls.public = env.ref("base.public_user")

    def block(self, **vals):
        base = {"name": "SF block", "website_id": self.website.id, "slot": "home.hero",
                "kind": "image", "image_desktop": png(), "alt_text": "A hero",
                "state": "published"}
        base.update(vals)
        return self.Block.create(base)


@tagged("post_install", "-at_install")
class TestContent(ContentFixture, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_content()

    def _site(self):
        return catalogue.public_site(self.website)

    # ------------------------------------------------------------ access

    def test_model_is_closed_to_public_and_portal(self):
        """Checked on the access mechanism, as a non-superuser environment,
        with internal users as controls (a blanket refusal is detectable)."""
        Block = self.Block
        for user in (self.public, self.portal):
            for operation in ("read", "write", "create", "unlink"):
                with self.assertRaises(AccessError, msg=(user.login, operation)):
                    Block.with_user(user).check_access(operation)
        Block.with_user(self.staff).check_access("read")
        with self.assertRaises(AccessError):
            Block.with_user(self.staff).check_access("write")
        for operation in ("read", "write", "create", "unlink"):
            Block.with_user(self.designer).check_access(operation)
        made = self.block().with_user(self.designer)
        made.headline = "Edited by a designer"
        self.assertEqual(made.headline, "Edited by a designer")

    def test_website_storefront_fields_are_not_public(self):
        Website = self.env["website"]
        for name in ("rz_storefront_refresh_requested_at", "rz_storefront_status"):
            field = Website._fields[name]
            for user in (self.public, self.portal):
                restricted = Website.with_user(user)
                # Control: an ordinary website field stays readable.
                self._assert_field_readable(restricted, "name")
                with self.assertRaises(AccessError, msg=(name, user.login)):
                    self._check_field(restricted, field.name)
        self._check_field(Website.with_user(self.designer), "rz_storefront_status")
        with self.assertRaises(AccessError):
            self._check_field(Website.with_user(self.staff), "rz_storefront_status")

    def _check_field(self, model, name):
        if hasattr(model, "check_field_access"):  # 18/20: check_field_access on 20
            model.check_field_access(model._fields[name], "read")
        else:
            model.check_field_access_rights("read", [name])

    def _assert_field_readable(self, model, name):
        self._check_field(model, name)

    # ------------------------------------------------------------ validation

    def test_link_validation(self):
        good = ("/", "/shop", "/shop/category/sunglasses-7?order=name+asc", "/about-us#team",
                "https://example.com", "https://example.com/a?b=c")
        bad = ("//evil.example", "http://example.com", "javascript:alert(1)", "https://",
               "https://user:pw@example.com", "/a b", "/a\\b", "/a\nb", "ftp://example.com",
               "example.com", "https://example.com:99999", "/" + "a" * 500, "data:text/html,x",
               '/shop"onmouseover=alert(1)', "/shop<script>", "/caf\u00e9", "/a{b}", "/a|b",
               "https://example.com/'x'")
        for link in good:
            self.assertTrue(storefront_block.link_ok(link), link)
            self.block(link=link, button_label="Shop")
        for link in bad:
            self.assertFalse(storefront_block.link_ok(link), link)
            with self.assertRaises(ValidationError, msg=link):
                self.block(link=link)

    def test_text_limits_and_button_needs_link(self):
        for field, limit in storefront_block.TEXT_LIMITS.items():
            if field == "link":
                continue
            extra = {"link": "/shop"} if field == "button_label" else {}
            self.block(**{field: "x" * limit}, **extra)
            with self.assertRaises(ValidationError, msg=field):
                self.block(**{field: "x" * (limit + 1)}, **extra)
        with self.assertRaises(ValidationError) as cm:
            self.block(button_label="Shop now")
        self.assertIn("needs a link", str(cm.exception))

    def test_slot_rules(self):
        self.block(slot="page.top", page_key="faq")
        with self.assertRaises(ValidationError):
            self.block(slot="page.top")
        with self.assertRaises(ValidationError):
            self.block(slot="home.hero", page_key="faq")
        self.block(slot="category.banner", category_id=self.category.id)
        with self.assertRaises(ValidationError):
            self.block(slot="home.hero", category_id=self.category.id)
        with self.assertRaises(ValueError):
            self.block(slot="home.secret_slot")

    def test_kind_requirements(self):
        with self.assertRaises(ValidationError):
            self.block(image_desktop=False)
        with self.assertRaises(ValidationError):
            self.block(alt_text="  ")
        with self.assertRaises(ValidationError):
            self.block(kind="video", image_desktop=False)
        with self.assertRaises(ValidationError):
            self.block(kind="text", image_desktop=False, alt_text=False)
        self.block(kind="text", image_desktop=False, alt_text=False, headline="Sale on")

    def test_images_must_be_png_jpeg_gif_or_webp(self):
        """By content. Core lets a system user (this test runs as one) put SVG
        in an image field; SVG can carry script, so it is refused here."""
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        for field in ("image_desktop", "image_mobile", "video_poster"):
            with self.assertRaises(UserError, msg=field):
                self.block(**{field: blob(svg)})
        buf = io.BytesIO()
        Image.new("RGB", (4, 4)).save(buf, format="JPEG")
        self.block(image_desktop=blob(buf.getvalue()))
        self.block(image_desktop=png())
        self.assertEqual(storefront_block.image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 "), "webp")
        self.assertEqual(storefront_block.image_type(b"GIF89a\x01\x00"), "gif")
        self.assertIsNone(storefront_block.image_type(svg[:16]))

    def test_non_image_upload_is_refused(self):
        with self.assertRaises(UserError):  # ValidationError is a UserError too
            self.block(image_desktop=blob(b"this is not an image at all"))

    def test_dates_must_be_ordered(self):
        now = fields.Datetime.now()
        with self.assertRaises(ValidationError):
            self.block(date_start=now, date_end=now)
        self.block(date_start=now, date_end=now + timedelta(hours=1))

    def test_video_is_checked_by_content_type_and_size(self):
        def video(raw, name):
            return self.block(kind="video", image_desktop=False, video=blob(raw),
                              video_filename=name, slot="home.video_band")

        self.assertEqual(storefront_block.video_type(MP4[:16]), "mp4")
        self.assertEqual(storefront_block.video_type(WEBM[:16]), "webm")
        video(MP4, "clip.mp4")
        video(WEBM, "clip.webm")
        for name in (False, "clip", "clip.mov"):
            with self.assertRaises(ValidationError, msg=name):
                video(MP4, name)
        for raw, name in ((raw_png(), "clip.mp4"), (b"GIF89a" + b"\x00" * 50, "clip.webm"),
                          (MP4, "clip.webm"), (WEBM, "clip.mp4")):
            with self.assertRaises(ValidationError, msg=name):
                video(raw, name)
        with patch.object(storefront_block, "MAX_VIDEO_BYTES", 100):
            with self.assertRaises(ValidationError) as cm:
                video(MP4, "clip.mp4")
        self.assertIn("larger than", str(cm.exception))

    def test_video_head_is_read_from_the_filestore(self):
        """16 bytes are read from the file; the 25 MB value is never loaded."""
        block = self.block(kind="video", image_desktop=False, video=blob(MP4),
                           video_filename="clip.mp4", slot="home.video_band")
        attachment = block._attachment("video")
        self.assertTrue(attachment.store_fname, "fixture: stored in the filestore")

        def no_raw(record):
            raise AssertionError("the whole attachment was loaded")

        with patch.object(type(attachment), "raw", property(no_raw)):
            self.assertEqual(storefront_block.attachment_head(attachment), MP4[:16])

    # ------------------------------------------------------------ live window

    def test_live_window(self):
        now = fields.Datetime.now()
        hour = timedelta(hours=1)
        live = self.block(name="live")
        started = self.block(name="started", date_start=now - hour, date_end=now + hour)
        future = self.block(name="future", date_start=now + hour)
        ended = self.block(name="ended", date_end=now - hour)
        ends_now = self.block(name="ends now", date_end=now)
        draft = self.block(name="draft", state="draft")
        archived = self.block(name="archived")
        archived.active = False
        other_site = self.block(name="other site", website_id=self.other_website.id)
        visible_banner = self.block(name="banner", slot="category.banner",
                                    category_id=self.category.id)
        hidden_banner = self.block(name="hidden banner", slot="category.banner",
                                   category_id=self.foreign_category.id)
        got = content.live_blocks(self._site(), now)
        mine = got & (live | started | future | ended | ends_now | draft | archived
                      | other_site | visible_banner | hidden_banner)
        self.assertEqual(mine, live | started | visible_banner)
        # The backend "Live now" column (compute) follows the same rule.
        self.assertTrue(live.is_live)
        for block in (draft, future, ended, ends_now):
            self.assertFalse(block.is_live, block.name)
        # The same rule as the "Live now" filter in the backend.
        searched = self.Block.search([("is_live", "=", True), ("id", "in", (
            live | future | ended | draft).ids)])
        self.assertEqual(searched, live)
        self.assertEqual(self.Block.search([("is_live", "=", False), ("id", "in", (
            live | future | ended | draft).ids)]), future | ended | draft)

    def test_meta_reports_version_refresh_and_next_change(self):
        site = self._site()
        now = fields.Datetime.now().replace(microsecond=0)
        before = content.meta_fields(site, now)
        self.assertIsNone(before["refresh_requested_at"])
        block = self.block(state="draft")
        self.assertEqual(content.meta_fields(site, now)["content_version"],
                         before["content_version"], "a draft changes nothing")
        block.state = "published"
        after = content.meta_fields(site, now)
        self.assertNotEqual(after["content_version"], before["content_version"])
        block.headline = "Changed"
        self.assertNotEqual(content.meta_fields(site, now)["content_version"],
                            after["content_version"])
        soon, later = now + timedelta(hours=2), now + timedelta(hours=5)
        self.block(date_start=later)
        self.block(date_start=now - timedelta(hours=1), date_end=soon)
        self.assertEqual(content.meta_fields(site, now)["next_content_change_at"],
                         catalogue._iso(soon))
        self.website.with_user(self.designer).action_rz_storefront_refresh()
        self.assertTrue(content.meta_fields(site, now)["refresh_requested_at"])
        self.assertEqual(set(catalogue.meta(site)) >= {
            "content_version", "refresh_requested_at", "next_content_change_at"}, True)

    def test_refresh_button_needs_website_designer(self):
        for user in (self.staff, self.portal):
            with self.assertRaises(AccessError, msg=user.login) as cm:
                self.website.with_user(user).action_rz_storefront_refresh()
            self.assertIn("Only website designers", str(cm.exception))
        self.assertFalse(self.website.rz_storefront_refresh_requested_at)
        self.website.with_user(self.designer).action_rz_storefront_refresh()
        self.assertTrue(self.website.rz_storefront_refresh_requested_at)

    # ------------------------------------------------------------ export

    def test_payload_shape_and_media_urls(self):
        # Larger than every size step, so each resized copy really exists.
        block = self.block(image_desktop=blob(raw_png(3000, 40)),
                           image_mobile=blob(raw_png(1600, 40)), headline="Hello",
                           link="/shop", button_label="Shop")
        self.block(name="draft", state="draft", headline="Secret draft")
        data = content.content_payload(self._site())
        self.assertEqual(set(data), {"contract", "generated_at", "website_id",
                                     "content_version", "blocks"})
        rows = [r for r in data["blocks"] if r["id"] == block.id]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(set(row), {"id", "slot", "page_key", "category_id", "kind", "sequence",
                                    "headline", "body", "button_label", "link", "alt",
                                    "date_start", "date_end", "media"})
        self.assertNotIn("Secret draft", str(data))
        sums = content.checksums(block)
        base = "https://sf-test.example"
        self.assertEqual([m["width"] for m in row["media"]["image_desktop"]], [640, 1280, 2560])
        self.assertEqual(row["media"]["image_desktop"][-1]["url"],
                         base + "/storefront-media/%d/image_desktop/%s"
                         % (block.id, sums[(block.id, "image_desktop")]))
        self.assertEqual([m["width"] for m in row["media"]["image_mobile"]], [720, 1440])
        self.assertEqual(data["content_version"], content.content_version(self._site()))

    def test_status_fetch_reaches_only_global_addresses_on_port_443(self):
        made = []

        class Pool:
            def __init__(self, host, port, **kwargs):
                made.append((host, port, kwargs.get("server_hostname"),
                             kwargs.get("assert_hostname")))

            def request(self, method, url, **kwargs):
                made.append((method, url, kwargs["headers"]["Host"]))

                class Res:
                    status = 200

                    def read(self, amount, decode_content=False):
                        return b'{"commit": "abc"}'

                    def close(self):
                        pass

                return Res()

        url = "https://sf-test.example/__sf/status"
        with patch.object(content.urllib3, "HTTPSConnectionPool", Pool):
            for addresses in (["10.0.0.5"], ["127.0.0.1"], ["169.254.169.254"], ["::1"],
                              ["93.184.216.34", "192.168.1.2"], []):
                with patch.object(content, "_resolve", lambda host, a=addresses: a):
                    self.assertIsNone(content._open_status(url), addresses)
            self.assertEqual(made, [], "no connection to a non-global address")
            self.assertIsNone(content._open_status("https://sf-test.example:8443/__sf/status"))
            self.assertIsNone(content._open_status("http://sf-test.example/__sf/status"))
            with patch.object(content, "_resolve", lambda host: ["93.184.216.34"]):
                self.assertEqual(content._open_status(url), {"commit": "abc"})
        self.assertEqual(made, [("93.184.216.34", 443, "sf-test.example", "sf-test.example"),
                                ("GET", "/__sf/status", "sf-test.example")])
        calls = []
        self.website.domain = "https://sf-test.example:8443"
        with patch.object(content, "_open_status", lambda u: calls.append(u)):
            self.assertIsNone(content.build_status(self.website))
        self.assertEqual(calls, [], "a port other than 443 is never contacted")

    def test_status_fetch_has_a_hard_deadline(self):
        import threading
        import time
        release = threading.Event()
        self.addCleanup(release.set)

        def hung(url):
            release.wait(10)
            return {"commit": "late"}

        with patch.object(content, "_open_status", hung), \
                patch.object(content, "STATUS_TIMEOUT", 0.2):
            begin = time.monotonic()
            text = content.build_status_text(self.website)
            elapsed = time.monotonic() - begin
        self.assertTrue(text.startswith("Unknown"))
        self.assertLess(elapsed, 1.5, "the form waited for a hung status fetch")

    def test_status_text(self):
        site = self._site()
        current = content.content_version(site)
        calls = []

        def fake(url):
            calls.append(url)
            return {"built_at": "2026-11-25T01:00:00Z", "commit": "abc123",
                    "content_version": current, "catalogue_hash": "x"}

        with patch.object(content, "_open_status", fake):
            text = content.build_status_text(self.website)
        self.assertEqual(calls, ["https://sf-test.example/__sf/status"])
        self.assertIn("abc123", text)
        self.assertIn("up to date", text)
        with patch.object(content, "_open_status", lambda url: {"content_version": "old"}):
            self.assertIn("older than Odoo", content.build_status_text(self.website))

        def broken(url):
            raise TimeoutError("slow")

        for failing in (broken, lambda url: None, lambda url: ["not", "a", "dict"]):
            with patch.object(content, "_open_status", failing):
                self.assertTrue(content.build_status_text(self.website).startswith("Unknown"))
        self.website.domain = False
        with patch.object(content, "_open_status", fake):
            self.assertTrue(content.build_status_text(self.website).startswith("Unknown"))
        self.assertEqual(len(calls), 1, "no request without a domain")


@tagged("post_install", "-at_install")
class TestContentHttp(ContentFixture, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_content()
        cls.website.domain = cls.base_url()

    def _get(self, path, token=TOKEN, headers=None):
        hdrs = dict(headers or {})
        if token:
            hdrs["X-Storefront-Token"] = token
        return self.opener.get(self.base_url() + path, headers=hdrs, allow_redirects=False,
                               timeout=60)

    def _assert_404(self, res, what):
        self.assertEqual(res.status_code, 404, what)
        self.assertEqual(res.json(), {"error": "not_found"}, what)
        self.assertNotIn("Set-Cookie", res.headers, what)

    def test_content_endpoint_uses_the_same_gate(self):
        live = self.block(headline="Live block")
        self.block(name="draft", state="draft", headline="Draft block")
        self._assert_404(self._get("/storefront/v1/content", token=None), "no token")
        self._assert_404(self._get("/storefront/v1/content", token="wrong" * 8), "bad token")
        self._assert_404(self._get("/storefront/v1/content?x=1"), "unknown parameter")
        res = self._get("/storefront/v1/content")
        self.assertEqual(res.status_code, 200, res.text[:300])
        ids = [b["id"] for b in res.json()["blocks"]]
        self.assertIn(live.id, ids)
        self.assertNotIn("Draft block", res.text)
        access.reset_cache()
        self.addCleanup(access.reset_cache)
        self._set_access(TEAM, "%d:%s" % (self.website.id, AUD))
        self._assert_404(self._get("/storefront/v1/content"), "Access configured, no JWT")

    def test_media_is_served_only_under_its_own_website_host(self):
        """A live block of another website is never served under this
        website's Host, though it is live on its own site."""
        mine = self.block(name="mine")
        theirs = self.block(name="theirs", website_id=self.other_website.id)
        self.assertTrue(content.is_live(theirs), "fixture: live on its own website")
        for block, expected in ((mine, 200), (theirs, 404)):
            path = content.media_path(block.id, "image_desktop",
                                      content.checksums(block)[(block.id, "image_desktop")])
            res = self.opener.get(self.base_url() + path, timeout=60)
            self.assertEqual(res.status_code, expected, block.name)
        self.website.domain = "https://elsewhere.example"     # Host names no website now
        path = content.media_path(mine.id, "image_desktop",
                                  content.checksums(mine)[(mine.id, "image_desktop")])
        self._assert_404(self.opener.get(self.base_url() + path, timeout=60), "unknown host")

    def test_media_is_served_only_for_live_blocks(self):
        block = self.block(kind="video", image_desktop=False, video=blob(MP4),
                           video_filename="clip.mp4", video_poster=png(), slot="home.video_band")
        data = content.content_payload(catalogue.public_site(self.website))
        row = [r for r in data["blocks"] if r["id"] == block.id][0]
        video_url = row["media"]["video"]["url"]
        poster_url = row["media"]["video_poster"][0]["url"]
        self.assertTrue(video_url.startswith(self.base_url() + "/storefront-media/"))
        for url, kind in ((video_url, "video/mp4"), (poster_url, "image/")):
            res = self.opener.get(url, timeout=60)
            self.assertEqual(res.status_code, 200, url)
            self.assertTrue(res.headers["Content-Type"].startswith(kind), res.headers)
            self.assertIn("immutable", res.headers.get("Cache-Control", ""))
            self.assertNotIn("Set-Cookie", res.headers)
        self.assertEqual(self.opener.get(video_url, timeout=60).content, MP4)
        path = video_url[len(self.base_url()):]
        prefix = path.rsplit("/", 1)[0]
        self._assert_404(self.opener.get(self.base_url() + prefix + "/" + "0" * 40, timeout=60),
                         "wrong checksum")
        name_url = "/storefront-media/%d/name/%s" % (block.id, path.rsplit("/", 1)[1])
        self._assert_404(self.opener.get(self.base_url() + name_url, timeout=60), "not media")
        self._assert_404(self.opener.get(video_url + "?x=1", timeout=60), "parameter")
        block.state = "draft"
        self._assert_404(self.opener.get(video_url, timeout=60), "draft")
        block.write({"state": "published", "date_start": fields.Datetime.now() + timedelta(days=1)})
        self._assert_404(self.opener.get(video_url, timeout=60), "not started")
        block.date_start = False
        self.assertEqual(self.opener.get(video_url, timeout=60).status_code, 200, "control")
        self.website.ecommerce_access = "logged_in"
        self._assert_404(self.opener.get(video_url, timeout=60), "shop closed to visitors")
