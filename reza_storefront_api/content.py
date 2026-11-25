# -*- coding: utf-8 -*-
"""Storefront content export (contract v1, "content" section of
docs/STOREFRONT_CATALOGUE_CONTRACT.md) and the "last published" status.

Plain module functions, like catalogue.py: nothing here is on a model, so
nothing is reachable over RPC. The controller calls them only after the gate
(token, optional Cloudflare Access JWT, Host, open shop).

Blocks are read with sudo() (public users have no access to the model), but
only blocks of the requested website that are published, active and inside
their date window at `now` ever leave this file, and only the keys written
out below.
"""

import hashlib
import ipaddress
import json
import logging
import socket
import threading

import certifi
import urllib3

from urllib.parse import urlsplit

from odoo import fields

from . import catalogue
from .models import storefront_block

_logger = logging.getLogger(__name__)

BLOCK = "reza.storefront.block"
MEDIA_PREFIX = "/storefront-media"
# field -> (media key, nominal width). The site picks a size from these.
IMAGE_FIELDS = {
    "image_desktop": ("image_desktop", 2560),
    "image_desktop_1280": ("image_desktop", 1280),
    "image_desktop_640": ("image_desktop", 640),
    "image_mobile": ("image_mobile", 1440),
    "image_mobile_720": ("image_mobile", 720),
    "video_poster": ("video_poster", 1920),
}
MEDIA_FIELDS = frozenset(IMAGE_FIELDS) | {"video"}
STATUS_PATH = "/__sf/status"
STATUS_TIMEOUT = 2
STATUS_MAX_BYTES = 16384


def _blocks(site):
    return site.env[BLOCK].sudo().with_context(active_test=True).search(
        [("website_id", "=", site.id), ("state", "=", "published")],
        order="slot, sequence, id")


def live_blocks(site, now=None):
    """Published, active, in-window blocks of this website. A category
    banner whose category the public cannot see on this site is left out."""
    now = now or fields.Datetime.now()
    visible = set(catalogue._public_categories(site).ids)
    return _blocks(site).filtered(
        lambda b: b._live_at(now) and (not b.category_id or b.category_id.id in visible))


def is_live(block, now=None):
    """The media controller's test: the same rule as the export."""
    site = catalogue.public_site(block.website_id)
    return (site is not None and catalogue.shop_open(site)
            and block in live_blocks(site, now))


def checksums(blocks):
    """{(block id, field): attachment checksum} for every stored media field."""
    # Resized copies are stored computed fields: make sure they are written.
    blocks.flush_recordset()
    rows = blocks.env["ir.attachment"].sudo().search_read([
        ("res_model", "=", BLOCK), ("res_id", "in", blocks.ids),
        ("res_field", "in", sorted(MEDIA_FIELDS))], ["res_id", "res_field", "checksum"])
    return {(r["res_id"], r["res_field"]): r["checksum"] for r in rows}


def video_mimetype(block):
    """video/mp4 or video/webm, from the validated file name, else from the
    file's first bytes (the constraint guarantees the two agree)."""
    name = (block.video_filename or "").lower()
    kind = name.rsplit(".", 1)[-1] if "." in name else None
    if kind not in storefront_block.VIDEO_TYPES:
        attachment = block._attachment("video")
        kind = (storefront_block.video_type(storefront_block.attachment_head(attachment))
                if attachment else None)
    return storefront_block.VIDEO_TYPES.get(kind)


def media_path(block_id, field, checksum):
    return "%s/%d/%s/%s" % (MEDIA_PREFIX, block_id, field, checksum)


def _base(site):
    payload = catalogue.website_payload(site)
    return (payload["domain"] or "").rstrip("/")


def _block_payload(block, base, sums):
    media = {}
    for field, (key, width) in IMAGE_FIELDS.items():
        checksum = sums.get((block.id, field))
        if checksum:
            media.setdefault(key, []).append(
                {"width": width, "url": base + media_path(block.id, field, checksum)})
    for key in media:
        media[key].sort(key=lambda m: m["width"])
    checksum = sums.get((block.id, "video"))
    if checksum:
        media["video"] = {"url": base + media_path(block.id, "video", checksum),
                          "mimetype": video_mimetype(block)}
    return {
        "id": block.id,
        "slot": block.slot,
        "page_key": block.page_key or None,
        "category_id": block.category_id.id or None,
        "kind": block.kind,
        "sequence": block.sequence,
        "headline": block.headline or None,
        "body": block.body or None,
        "button_label": block.button_label or None,
        "link": block.link or None,
        "alt": block.alt_text or None,
        "date_start": catalogue._iso(block.date_start),
        "date_end": catalogue._iso(block.date_end),
        "media": media,
    }


def content_payload(site, now=None):
    blocks = live_blocks(site, now)
    sums = checksums(blocks)
    base = _base(site)
    rows = [_block_payload(block, base, sums) for block in blocks]
    return {
        "contract": catalogue.CONTRACT,
        "generated_at": catalogue._iso(fields.Datetime.now()),
        "website_id": site.id,
        "content_version": _version(rows),
        "blocks": rows,
    }


def _version(rows):
    text = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def content_version(site, now=None):
    blocks = live_blocks(site, now)
    sums = checksums(blocks)
    base = _base(site)
    return _version([_block_payload(block, base, sums) for block in blocks])


def next_change(site, now=None):
    """The next moment the live set changes on its own (a start or an end in
    the future), so the build server can schedule a rebuild. None if none."""
    now = now or fields.Datetime.now()
    moments = []
    for block in _blocks(site):
        moments += [d for d in (block.date_start, block.date_end) if d and d > now]
    return min(moments) if moments else None


def meta_fields(site, now=None):
    # refresh_requested_at means "a designer asked for a rebuild at this
    # time": the build server compares it with its last build and rebuilds
    # when it is newer. It is never a schedule (next_content_change_at is).
    refresh = site.sudo().rz_storefront_refresh_requested_at
    return {
        "content_version": content_version(site, now),
        "refresh_requested_at": catalogue._iso(refresh),
        "next_content_change_at": catalogue._iso(next_change(site, now)),
    }


# ---------------------------------------------------------------- status

def _resolve(host):
    """Every address the host resolves to, for HTTPS."""
    return sorted({info[4][0] for info in socket.getaddrinfo(
        host, 443, type=socket.SOCK_STREAM)})


def _global_address(host):
    """One address of host, only if EVERY address it resolves to is a global
    (public) one: no loopback, private, link-local or metadata address can
    be reached through a website's domain."""
    addresses = _resolve(host)
    if not addresses:
        return None
    for address in addresses:
        if not ipaddress.ip_address(address).is_global:
            return None
    return addresses[0]


def _open_status(url):
    """GET url: HTTPS on port 443 to a global address only, certificate
    verified against the host name, no redirect, no retry. The connection
    goes to the address that was checked (no second DNS lookup)."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme != "https" or not host or parts.port not in (None, 443):
        return None
    address = _global_address(host)
    if address is None:
        return None
    pool = urllib3.HTTPSConnectionPool(
        address, 443, cert_reqs="CERT_REQUIRED", ca_certs=certifi.where(),
        server_hostname=host, assert_hostname=host, retries=False)
    res = pool.request(
        "GET", parts.path or "/", headers={"Host": host, "Accept": "application/json",
                                           "Accept-Encoding": "identity"},
        timeout=urllib3.Timeout(total=STATUS_TIMEOUT), redirect=False, retries=False,
        preload_content=False, decode_content=False)
    try:
        if res.status != 200:
            return None
        body = res.read(STATUS_MAX_BYTES + 1, decode_content=False)
    finally:
        res.close()
    if len(body) > STATUS_MAX_BYTES:
        return None
    return json.loads(body.decode("utf-8"))


def build_status(website):
    """The storefront's own /__sf/status for this website's domain, or None.
    Only the configured domain is contacted, over HTTPS."""
    authority = catalogue._configured_authority(website.sudo().domain)
    if not authority or ":" in authority:  # no domain, or a port other than 443
        return None
    box = {}

    def run():
        try:
            box["value"] = _open_status("https://%s%s" % (authority, STATUS_PATH))
        except Exception as exc:  # noqa: BLE001 - "unknown" on any failure
            box["error"] = type(exc).__name__

    # Hard bound for the form, DNS included: the fetch runs in a daemon
    # thread that is abandoned after STATUS_TIMEOUT seconds.
    thread = threading.Thread(target=run, name="storefront-status", daemon=True)
    thread.start()
    thread.join(STATUS_TIMEOUT)
    if thread.is_alive() or "error" in box:
        _logger.info("storefront status unavailable for website %s: %s", website.id,
                     box.get("error", "timeout"))
        return None
    status = box.get("value")
    return status if isinstance(status, dict) else None


def build_status_text(website):
    status = build_status(website)
    if not status:
        return "Unknown: the storefront did not answer."
    site = catalogue.public_site(website)
    current = content_version(site) if site else None
    published = status.get("content_version")
    lines = [
        "Built at: %s" % (status.get("built_at") or "unknown"),
        "Commit: %s" % (status.get("commit") or "unknown"),
        "Content: %s" % ("up to date" if published and published == current
                         else "older than Odoo (refresh to publish)"),
    ]
    return "\n".join(str(line)[:200] for line in lines)
