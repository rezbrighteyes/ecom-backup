# -*- coding: utf-8 -*-
"""Storefront content: hand-placed images, videos and text for the static
storefront, per website and per fixed slot.

Access (security/): website designers read and write, other internal users
read, and NOTHING for public or portal users. The public storefront reaches
a block only through the export (content.py, behind the same gate as the
catalogue) and its media only through /storefront-media/ (controllers),
which serves a block only while it is published and in its date window.

No public method: validation runs in constraints, and the "active now"
filter in a private search method.
"""

import re
from urllib.parse import urlsplit

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# The slots the storefront renders. Fixed in code: the site side builds a
# place for each, and a slot nobody renders is a block nobody sees.
SLOTS = [
    ("home.hero", "Home: hero"),
    ("home.promo_strip", "Home: promo strip"),
    ("home.video_band", "Home: video band"),
    ("home.editorial_1", "Home: editorial 1"),
    ("home.editorial_2", "Home: editorial 2"),
    ("home.editorial_3", "Home: editorial 3"),
    ("category.banner", "Category: banner"),
    ("page.top", "Page: top"),
    ("site.promo_bar", "Site: promo bar"),
]
PAGES = [
    ("about-us", "About us"),
    ("delivery", "Delivery"),
    ("returns", "Returns"),
    ("warranty", "Warranty"),
    ("faq", "FAQ"),
    ("contactus", "Contact us"),
    ("privacy", "Privacy"),
    ("terms", "Terms"),
]
KINDS = [("image", "Image"), ("video", "Video"), ("text", "Text")]
TEXT_LIMITS = {"name": 120, "headline": 120, "body": 600, "button_label": 40,
               "alt_text": 200, "link": 500}
MAX_VIDEO_BYTES = 25 * 1024 * 1024
# Video containers, recognised by their first bytes, never by the file name.
VIDEO_TYPES = {
    "mp4": "video/mp4",     # ISO base media: bytes 4..8 are "ftyp"
    "webm": "video/webm",   # EBML header 1A 45 DF A3
}
_CONTROL = re.compile(r"[\x00-\x20\x7f\\]")
# RFC 3986 characters only: no quote, angle bracket, brace, space or non-ASCII
# can reach an attribute or a URL the site writes out.
_URI_CHARS = re.compile(r"[A-Za-z0-9\-._~:/?#\[\]@!$&()*+,;=%]+", re.ASCII)
IMAGE_FIELDS = ("image_desktop", "image_desktop_1280", "image_desktop_640", "image_mobile",
                "image_mobile_720", "video_poster")


def image_type(head):
    """'png', 'jpeg', 'gif', 'webp' or None, from the first bytes. SVG (which
    can carry script) and everything else is refused."""
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def video_type(head):
    """'mp4', 'webm' or None, from the first bytes of a file."""
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"
    return None


def attachment_head(attachment, size=16):
    """The first bytes of an attachment, read from the filestore file when it
    is stored there, so a 25 MB video is never loaded to check 16 bytes.
    Otherwise from the record. 18/20: raw is bytes on 18, a file-like
    BinaryValue on 20."""
    if attachment.store_fname:
        with open(attachment._full_path(attachment.store_fname), "rb") as stream:
            return stream.read(size)
    raw = attachment.raw
    if hasattr(raw, "open"):
        with raw.open() as stream:
            return stream.read(size)
    return bytes(raw[:size])


def link_ok(link):
    """A site path ("/shop/...", never "//host") or an https URL with a host
    and no user info. No spaces, control characters or backslashes."""
    if not link or len(link) > TEXT_LIMITS["link"] or _CONTROL.search(link):
        return False
    if not _URI_CHARS.fullmatch(link):
        return False
    if link.startswith("/"):
        return not link.startswith("//")
    try:
        parts = urlsplit(link)
        port = parts.port
    except ValueError:
        return False
    del port
    return (parts.scheme == "https" and bool(parts.hostname)
            and not parts.username and not parts.password)


class StorefrontBlock(models.Model):
    _name = "reza.storefront.block"
    _description = "Storefront content block"
    _order = "website_id, slot, sequence, id"

    name = fields.Char(required=True, help="Internal label, not shown on the site.")
    website_id = fields.Many2one("website", required=True, ondelete="cascade", index=True)
    slot = fields.Selection(SLOTS, required=True, index=True)
    page_key = fields.Selection(PAGES, help="Page slot only: which page.")
    category_id = fields.Many2one(
        "product.public.category", ondelete="cascade",
        help="Category banner only: empty means every category page.")
    kind = fields.Selection(KINDS, required=True, default="image")
    state = fields.Selection(
        [("draft", "Draft"), ("published", "Published")], required=True, default="draft",
        index=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    date_start = fields.Datetime(help="Shown from this moment (UTC). Empty: at once.")
    date_end = fields.Datetime(help="Hidden from this moment (UTC). Empty: never.")

    image_desktop = fields.Image(max_width=2560, max_height=2560)
    image_desktop_1280 = fields.Image(related="image_desktop", max_width=1280,
                                      max_height=1280, store=True)
    image_desktop_640 = fields.Image(related="image_desktop", max_width=640,
                                     max_height=640, store=True)
    image_mobile = fields.Image(max_width=1440, max_height=1440)
    image_mobile_720 = fields.Image(related="image_mobile", max_width=720,
                                    max_height=720, store=True)
    video = fields.Binary(attachment=True, help="MP4 or WebM, 25 MB at most.")
    video_filename = fields.Char()
    video_poster = fields.Image(max_width=1920, max_height=1920)

    headline = fields.Char()
    body = fields.Text()
    button_label = fields.Char()
    link = fields.Char(help='A site path starting with "/" or an https:// address.')
    alt_text = fields.Char(help="Describes the image or video for screen readers.")

    is_live = fields.Boolean(
        string="Live now", compute="_compute_is_live", search="_search_is_live",
        help="Published, active and inside its date window right now.")

    # ------------------------------------------------------------ live

    def _live_at(self, when):
        self.ensure_one()
        return (self.active and self.state == "published"
                and (not self.date_start or self.date_start <= when)
                and (not self.date_end or when < self.date_end))

    def _compute_is_live(self):
        now = fields.Datetime.now()
        for block in self:
            block.is_live = block._live_at(now)

    def _search_is_live(self, operator, value):
        if operator not in ("=", "!=") or not isinstance(value, bool):
            raise ValidationError(_("Unsupported search on Live now."))
        now = fields.Datetime.now()
        live = ["&", "&", ("state", "=", "published"),
                "|", ("date_start", "=", False), ("date_start", "<=", now),
                "|", ("date_end", "=", False), ("date_end", ">", now)]
        if (operator == "=") == value:
            return live
        return ["|", "|", ("state", "!=", "published"),
                ("date_start", ">", now), ("date_end", "<=", now)]

    # ------------------------------------------------------------ validation

    def _attachment(self, field):
        return self.env["ir.attachment"].sudo().search([
            ("res_model", "=", self._name), ("res_field", "=", field),
            ("res_id", "=", self.id)], limit=1)

    @api.constrains("slot", "page_key", "category_id")
    def _check_slot(self):
        for block in self:
            if block.slot == "page.top" and not block.page_key:
                raise ValidationError(_("A page slot needs the page it belongs to."))
            if block.slot != "page.top" and block.page_key:
                raise ValidationError(_("Only a page slot takes a page."))
            if block.slot != "category.banner" and block.category_id:
                raise ValidationError(_("Only a category banner takes a category."))

    @api.constrains("name", "headline", "body", "button_label", "alt_text", "link")
    def _check_text(self):
        for block in self:
            for field, limit in TEXT_LIMITS.items():
                if len(block[field] or "") > limit:
                    raise ValidationError(_("%(field)s is longer than %(limit)s characters.",
                                            field=block._fields[field].string, limit=limit))
            if block.link and not link_ok(block.link):
                raise ValidationError(_(
                    'The link must be a site path starting with "/" or an https:// address.'))
            if block.button_label and not block.link:
                raise ValidationError(_("A button needs a link."))

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        for block in self:
            if block.date_start and block.date_end and block.date_end <= block.date_start:
                raise ValidationError(_("The end must be after the start."))

    @api.constrains("kind", "image_desktop", "video", "alt_text", "headline", "body")
    def _check_kind(self):
        for block in self:
            if block.kind == "image" and not block.image_desktop:
                raise ValidationError(_("An image block needs a desktop image."))
            if block.kind == "video" and not block.video:
                raise ValidationError(_("A video block needs a video."))
            if block.kind in ("image", "video") and not (block.alt_text or "").strip():
                raise ValidationError(_("Images and videos need alt text."))
            if block.kind == "text" and not (block.headline or block.body):
                raise ValidationError(_("A text block needs a headline or a body."))

    @api.constrains("video", "video_filename")
    def _check_video(self):
        for block in self:
            attachment = block._attachment("video")
            if not attachment:
                continue
            if attachment.file_size > MAX_VIDEO_BYTES:
                raise ValidationError(_("The video is larger than %s MB.",
                                        MAX_VIDEO_BYTES // (1024 * 1024)))
            name = (block.video_filename or "").lower()
            if not name.endswith((".mp4", ".webm")):
                raise ValidationError(_("The video file name must end in .mp4 or .webm."))
            found = video_type(attachment_head(attachment))
            if found is None:
                raise ValidationError(_("The video must be an MP4 or WebM file."))
            if not name.endswith("." + found):
                raise ValidationError(_("The file name does not match its content (%s).", found))

    @api.constrains(*IMAGE_FIELDS)
    def _check_images(self):
        """PNG, JPEG, GIF or WebP by their first bytes. Core lets a system
        user upload SVG into an image field; SVG can carry script, so it is
        refused here for everyone."""
        for block in self:
            for field in IMAGE_FIELDS:
                attachment = block._attachment(field)
                if attachment and image_type(attachment_head(attachment)) is None:
                    raise ValidationError(_("%s must be a PNG, JPEG, GIF or WebP image.",
                                            block._fields[field].string))
