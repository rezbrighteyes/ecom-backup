# -*- coding: utf-8 -*-
"""Storefront menu export ("menu" section of docs/STOREFRONT_CATALOGUE_CONTRACT.md).

Plain module functions, like catalogue.py and content.py: nothing here is on
a model, so nothing is reachable over RPC. The controller calls them only
after the gate (token, optional Cloudflare Access JWT, Host, open shop), and
content.py folds the menu into content_version so an edit triggers a rebuild.

The source is the website's own Odoo menu (website.menu under website.menu_id),
read ONLY when the website's "Use the Odoo menu" switch is on; otherwise the
export says "menu": null and the storefront keeps its automatic menu.

What leaves this file:
* items as the website's public user selects them: Odoo's own record rule
  on "Visible Groups" applies (a menu limited to groups the public user is not
  in is left out), and is_visible as that user (a menu on an unpublished
  page is left out);
* a link only when it passes the storefront's link rule (a site path or an
  https address, RFC 3986 characters only; storefront_block.link_ok), else
  the item is left out;
* "category_mega" only for a category the public can see on this website;
* one "brands_mega" at most (the storefront has one Brands panel);
* "drop" only with at least one valid sub-menu;
* featured brands of this website, active, that have a published product
  on it, in sequence order.
Everything is bounded (MAX_*), so an over-filled menu is cut, never served
unbounded.
"""

from odoo import fields

from . import catalogue
from .models.storefront_block import link_ok

FEATURED = "reza.storefront.featured.brand"
MAX_ITEMS = 12
MAX_CHILDREN = 30
MAX_FEATURED = 12
NAME_MAX = 60


def enabled(site):
    return bool(site.sudo().rz_storefront_use_odoo_menu)


def _name(menu):
    name = " ".join((menu.name or "").split())
    return name if 0 < len(name) <= NAME_MAX else None


def _public(menu):
    """Visible to the public user that selected it (record rules did groups)."""
    return menu.is_visible


def _badge(menu):
    badge = " ".join((menu.rz_badge or "").split())
    if not badge:
        return None, None
    return badge, menu.rz_badge_style or "promo"


def _link(menu):
    url = (menu.url or "").strip()
    return url if link_ok(url) else None


def _children(site, menu):
    rows = []
    kids = site.env["website.menu"].search([("parent_id", "=", menu.id)], order="sequence, id")
    for kid in kids:
        if len(rows) >= MAX_CHILDREN:
            break
        name, url = _name(kid), _link(kid)
        if not (_public(kid) and name and url):
            continue
        badge, style = _badge(kid.sudo())
        rows.append({"id": kid.id, "name": name, "url": url, "new_window": bool(kid.new_window),
                     "badge": badge, "badge_style": style})
    return rows


def items(site):
    root = site.menu_id
    if not root:
        return []
    visible_categories = set(catalogue._public_categories(site).ids)
    rows = []
    seen = set()
    tops = site.env["website.menu"].search([("parent_id", "=", root.id)], order="sequence, id")
    for menu in tops:
        if len(rows) >= MAX_ITEMS:
            break
        name = _name(menu)
        if not (_public(menu) and name):
            continue
        data = menu.sudo()
        kind = data.rz_kind or "link"
        row = {"id": menu.id, "name": name, "kind": kind, "url": None,
               "new_window": bool(menu.new_window), "category_id": None, "children": []}
        row["badge"], row["badge_style"] = _badge(data)
        if kind == "link":
            row["url"] = _link(menu)
            if not row["url"]:
                continue
        elif kind == "category_mega":
            categ = data.rz_public_categ_id.id
            if not categ or categ not in visible_categories or ("c", categ) in seen:
                continue
            seen.add(("c", categ))
            row["category_id"] = categ
        elif kind == "brands_mega":
            if "brands" in seen:
                continue
            seen.add("brands")
        elif kind == "drop":
            row["url"] = _link(menu)
            row["children"] = _children(site, menu)
            if not row["children"]:
                continue
        else:
            continue
        rows.append(row)
    return rows


def _brands_with_products(site):
    rows = catalogue._public_templates(site)._read_group(
        catalogue.product_domain(site), ["feed_brand_id"], [],
        limit=catalogue.MAX_META_ROWS + 1)
    if len(rows) > catalogue.MAX_META_ROWS:
        raise catalogue.PageTooLarge("brands", catalogue.MAX_META_ROWS)
    return {b.id for (b,) in rows if b}


def featured_brands(site):
    rows = site.env[FEATURED].sudo().with_context(active_test=True).search(
        [("website_id", "=", site.id)], order="sequence, id")
    stocked = _brands_with_products(site)
    slugify = site.env["ir.http"]._slugify
    out = []
    for row in rows:
        brand = row.brand_id
        if brand.id not in stocked or any(b["id"] == brand.id for b in out):
            continue
        out.append({"id": brand.id, "name": brand.name,
                    "slug": slugify(brand.name or "") or str(brand.id)})
        if len(out) >= MAX_FEATURED:
            break
    return out


def menu_payload(site):
    """The menu section, or None when the website does not use the Odoo menu."""
    if not enabled(site):
        return None
    return {"items": items(site), "featured_brands": featured_brands(site)}


def export(site):
    return {
        "contract": catalogue.CONTRACT,
        "generated_at": catalogue._iso(fields.Datetime.now()),
        "website_id": site.id,
        "menu": menu_payload(site),
    }
