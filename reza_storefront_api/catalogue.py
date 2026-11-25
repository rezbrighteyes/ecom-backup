# -*- coding: utf-8 -*-
"""Catalogue export, contract v1 (docs/STOREFRONT_CATALOGUE_CONTRACT.md).

Plain module functions, not model methods. Odoo performs no access check on an
RPC method call (only the method NAME is checked), so a model method that reads
with sudo() is reachable by any signed-in shopper. Nothing here is on a model;
only the controller in controllers/main.py calls these functions, and only
after the token, Host, shop-access and cookie checks.

Selection is done AS THE WEBSITE'S PUBLIC USER (record rules and access rules
apply: company, single-website, published, category visibility). sudo() is
used only afterwards, to read the contract fields of records that selection
already allowed. Every key that leaves this file is written out literally, so
a field added to product.template later (cost, Edbert codes, notes) cannot
leak by accident.

Odoo 20 version. The Odoo 18 copy differs only where marked "18/20".
"""

import hmac
import re
from urllib.parse import urlencode, urlparse, urlsplit

from odoo import SUPERUSER_ID, fields
from odoo.tools import SQL
from odoo.fields import Domain  # 18/20: odoo.osv.expression on 18

CONTRACT = 1
PARAM_TOKEN = "reza_storefront_api.token"
MIN_TOKEN_LENGTH = 32
DEFAULT_LIMIT = 200
MAX_LIMIT = 500
MAX_PAGE = 100000
# Work bound per request: a page whose templates expand to more variants than
# this is refused with a 400 that names the bound, so the build asks for a
# smaller `limit`. Nothing is silently dropped.
MAX_VARIANTS_PER_PAGE = 2500
# /meta has no paging in contract v1, so it is bounded the same way: more
# categories or brands than this is refused rather than served unbounded.
MAX_META_ROWS = 5000
# /shop's "Name (A-Z)" order as website_sale _get_search_order spells it.
NAME_ORDER = "is_published desc, name asc, id desc"
# Theme holding-page gates: a website method that answers True while the shop
# is shown to anonymous visitors as a holding page (YEO prelaunch on Odoo 18).
HOLDING_PAGE_GATES = ("_yeo_gate_on",)
# Internal references that must never reach an exported URL. A slug is built
# from display_name, and an addon such as d3_product_reference (Odoo 18) puts
# its second reference into display_name.
INTERNAL_REF_FIELDS = ("second_reference",)

_DIGITS = re.compile(r"[0-9]{1,7}", re.ASCII)
_HOST = re.compile(r"([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)(?::([0-9]{1,5}))?", re.ASCII)


class PageTooLarge(Exception):
    def __init__(self, what, bound):
        super().__init__(what, bound)
        self.what = what
        self.bound = bound


# ---------------------------------------------------------------- access

def token_ok(env, header_value):
    """True only when the header equals a configured token of 32+ characters.

    hmac.compare_digest("", "") is True, so both sides are checked for
    emptiness BEFORE the compare. Both are compared as UTF-8 bytes:
    compare_digest raises TypeError on a str holding non-ASCII text. A short
    configured token closes the endpoint rather than accepting a weak secret.
    """
    expected = env["ir.config_parameter"].sudo().get_str(PARAM_TOKEN) or ""  # 18/20: get_param on 18
    if not isinstance(expected, str) or len(expected.strip()) < MIN_TOKEN_LENGTH:
        return False
    if not header_value or not isinstance(header_value, str):
        return False
    return hmac.compare_digest(expected.encode("utf-8"), header_value.encode("utf-8"))


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _authority(host, port, scheme):
    """host[:port], with the port left out only when it is the default port
    of THIS scheme (443 for https, 80 for http), never the other one."""
    try:
        host = host.encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError):
        return ""
    if scheme not in _DEFAULT_PORTS:
        return ""
    if port is None or port == _DEFAULT_PORTS[scheme]:
        return host
    return "%s:%d" % (host, port)


def _configured_authority(domain):
    """The authority of a website's configured domain (a URL or a bare host).
    Anything beyond scheme://host[:port][/] makes it unusable for matching."""
    domain = (domain or "").strip()
    if not domain:
        return ""
    if "://" not in domain:
        domain = "https://" + domain
    try:
        parts = urlsplit(domain)
        port = parts.port
    except ValueError:
        return ""
    if (parts.path not in ("", "/") or parts.query or parts.fragment
            or parts.username or parts.password or not parts.hostname):
        return ""
    return _authority(parts.hostname, port, parts.scheme.lower())


def _request_authority(host, scheme):
    """The request's Host header as an authority: host[:port] and nothing
    else. A path, query, fragment, userinfo or any other URL syntax is
    refused instead of being parsed away."""
    match = _HOST.fullmatch((host or "").lower())
    if not match:
        return ""
    port = int(match.group(2)) if match.group(2) else None
    if port is not None and not 0 < port < 65536:
        return ""
    return _authority(match.group(1), port, scheme)


def website_for_host(env, host, scheme="https"):
    """The ONE website whose own domain equals the request Host, else empty.

    Odoo's normal resolution falls back to the first website for an unknown
    Host; this API does not. Two websites claiming the same host also give
    an empty result.
    """
    authority = _request_authority(host, scheme)
    Website = env["website"].sudo()
    if not authority:
        return Website
    matches = Website.search([]).filtered(
        lambda w: _configured_authority(w.domain) == authority)
    return matches if len(matches) == 1 else Website


def public_site(website):
    """The website as its public user, in a FRESH environment: exactly the
    website's company, its language, and nothing from the request context
    (editor flags such as edit_translations would otherwise change the
    exported HTML). None when the website's user is not a public user."""
    website = website.sudo()
    user = website.user_id
    if (not user or user.id == SUPERUSER_ID or not user._is_public()
            or website.company_id not in user.company_ids):
        return None
    env = website.env(user=user.id, su=False, context={
        "lang": website.default_lang_id.code or "en_US",
        "website_id": website.id,
        "allowed_company_ids": [website.company_id.id],
        "active_test": True,
    })
    return env["website"].browse(website.id)


def shop_open(site):
    """Open to an anonymous visitor: Odoo's own login-only check, and no theme
    holding page (YEO prelaunch) in front of the shop."""
    if not site.has_ecommerce_access():
        return False
    for gate in HOLDING_PAGE_GATES:
        check = getattr(site, gate, None)
        if check is not None and check():
            return False
    return True


def product_domain(site):
    """Templates this website sells to an anonymous visitor.

    sale_product_domain() is evaluated as the public user (core drops its
    is_published rule for an internal user). The explicit rules are ANDed on
    because the Odoo 18 sh_product_multi_website override returns only
    sale_ok + website_ids, with no publication or company rule. The company
    rule mirrors core's multi-company rule (parent_of, so a branch website
    still sells its parent company's products).
    """
    company = site.company_id
    return Domain.AND([
        Domain(site.sale_product_domain()),
        Domain([
            ("is_published", "=", True),
            ("sale_ok", "=", True),
            ("active", "=", True),
        ]),
        Domain(["|", ("company_id", "=", False), ("company_id", "parent_of", company.ids)]),
    ])


def _public_templates(site):
    """product.template as the public user: the search below applies the
    record rules (company, single website_id, publication) that sudo() would
    skip."""
    return site.env["product.template"].with_context(active_test=True)


def _sudo_templates(site, ids):
    return site.env["product.template"].sudo().with_context(
        website_id=site.id, lang=site.env.lang, active_test=True).browse(ids)


def name_ranks(site, domain, ids):
    """{id: position in /shop's name order} for `ids` only.

    PostgreSQL numbers the whole eligible set in the shop's own name order
    (its collation, the public user's record rules) and returns only the rows
    of this page, so the rows sent to Python are bounded by the page size.
    The database still sorts every eligible product once per page; that work
    stays in PostgreSQL. Ranks are consistent within one export run as long
    as no product is renamed or (un)published during it."""
    if not ids:
        return {}
    Templates = _public_templates(site)
    query = Templates._search(domain, order=NAME_ORDER)
    order = query.order
    query.order = None
    row_id = query.table.id  # 18/20: SQL.identifier(query.table, "id") on 18
    numbered = query.select(SQL("%s AS id, row_number() OVER (ORDER BY %s) AS position",
                                row_id, order))
    site.env.cr.execute(SQL(
        "SELECT numbered.id, numbered.position FROM (%s) AS numbered WHERE numbered.id = ANY(%s)",
        numbered, list(ids)))
    return dict(site.env.cr.fetchall())


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _iso_exact(dt):
    """Full precision (microseconds): a sort key must order exactly as the
    database does, and two products can be created in the same second."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if dt else None


def _sort_keys(template, price_hidden):
    """The fields /shop orders by (website_sale _get_search_order:
    "is_published desc, <sort>, id desc", <sort> from the website's
    shop_default_sort or ?order=): website_sequence (Featured), create_date
    (Newest on 18) / publish_date (Newest on 20), name, and list_price, the
    template's own sales price, NOT the pricelist price. The final tie-breaker
    is the product id, descending. 18/20: publish_date does not exist on 18.

    list_price is null whenever the shop hides any of this product's prices
    (hide_price, zero-price policy, a zero public price): the sort key must
    never reveal a base price the shop does not show."""
    publish = template["publish_date"] if "publish_date" in template._fields else None
    return {
        "website_sequence": template.website_sequence,
        "create_date": _iso_exact(template.create_date),
        "publish_date": _iso_exact(publish),
        "list_price": None if price_hidden else template.list_price,
    }


def _str_or_none(value):
    if not value:
        return None
    return str(value)


# ---------------------------------------------------------------- 18/20

def anonymous_pricing(site):
    """Pricelist and fiscal position of the website's public partner, with no
    session, no cart and no GeoIP.

    Same selection as website._get_and_cache_current_pricelist() /
    _get_and_cache_current_fiscal_position() for a fresh anonymous visitor
    whose country is unknown: website.get_pricelist_available(), the public
    partner's pricelist when it is among them, else the first one. The price arithmetic
    itself stays in Odoo (_get_combination_info / _get_sales_prices).
    """
    Pricelist = site.env["product.pricelist"].sudo()
    partner = site.env.user.partner_id.sudo()
    pricelist = Pricelist
    if site.env["res.groups"]._is_feature_enabled("product.group_product_pricelist"):
        # The visitor's own selection path, overrides included (a members-only
        # filter, for example). The caller has already neutralised what it
        # reads from the request: no session cookie is accepted and
        # request.geoip carries no country (see gate.neutralise_request).
        available = site.get_pricelist_available()
        pricelist = partner.specific_property_product_pricelist
        if pricelist not in available:
            pricelist = available[:1]
    fiscal_position = site.env["account.fiscal.position"].sudo()._get_fiscal_position(partner)
    return {"pricelist": pricelist.sudo(), "fiscal_position": fiscal_position.sudo()}


def apply_pricing(request, site, pricing):
    """Odoo 20 reads website.pricelist_id / currency_id / tax_display from
    request.pricelist. Set them, and an EMPTY cart, so nothing below can read
    or write a session cart."""
    if request is not None:
        request.pricelist = pricing["pricelist"]
        request.fiscal_position = pricing["fiscal_position"]
        request.cart = site.env["sale.order"].sudo()


def _website_prices_include_tax(website):
    return website.tax_display == "tax_included"


def _category_url(category):
    url = category.website_url
    return url if url and url != "#" else None


def _first_combination(template, variant):
    """The full combination the product page shows for this variant,
    including the default choice of every no-variant attribute."""
    combination = template._get_first_possible_combination(
        necessary_values=variant.product_template_attribute_value_ids)
    return combination or variant.product_template_attribute_value_ids


def _combination_info(template, variant, pricing):
    return template._get_combination_info(
        combination=_first_combination(template, variant),
        product_id=variant.id,
        add_qty=1.0,
        pricelist=pricing["pricelist"],
        fiscal_position=pricing["fiscal_position"],
    )


def _price_hidden(info):
    return bool(info.get("hide_price"))


def _effective_allow_out_of_stock(template, info):
    # Odoo 20's combination info carries no stock policy outside the product
    # page context; the template field is the shop's policy.
    return bool(template.allow_out_of_stock_order)


def _variant_qty(site, variant, info):
    return site.sudo()._get_product_available_qty(variant.sudo())


def _ribbons(site, templates, pricing):
    """The ribbon the shop grid shows: manual first, then auto-assigned."""
    prices = templates._get_sales_prices(
        pricing["pricelist"], pricing["fiscal_position"], site.sudo())
    auto = site.env["product.ribbon"].sudo().search_fetch([("assign", "!=", "manual")])
    return {t.id: t._get_ribbon(prices.get(t.id), auto) for t in templates}


# ---------------------------------------------------------------- shared

def _strike_price(info):
    """The price Odoo strikes through on the product page, or None.

    Mirrors website_sale's product_price template: list_price when a
    pricelist discount applies, else compare_list_price when it is above
    the price. A hidden price has no strike price either.
    """
    if _price_hidden(info):
        return None
    if info.get("has_discounted_price"):
        return info["list_price"]
    compare = info.get("compare_list_price")
    if compare and compare > info["price"]:
        return compare
    return None


def _band(template, allow_out_of_stock, qty):
    if allow_out_of_stock or not template.is_storable:
        return "in_stock"
    if qty <= 0:
        return "out"
    if qty <= (template.available_threshold or 0):
        return "low"
    return "in_stock"


def _internal_refs(template):
    refs = []
    for name in INTERNAL_REF_FIELDS:
        for records in (template, template.product_variant_ids):
            if name in records._fields:
                refs.extend(str(r[name]) for r in records if r[name])
    return refs


def _template_url(template):
    """Odoo's own product URL, unless its slug would carry an internal
    reference. Then the slug is rebuilt from the public name; if even that
    carries it (an seo_name typed with the reference), the URL is the id
    alone. Odoo resolves /shop/<anything>-<id> and /shop/<id> by the id."""
    url = template.website_url or ""
    slugify = template.env["ir.http"]._slugify
    refs = [slugify(r) for r in _internal_refs(template)]
    refs = [r for r in refs if r]

    def clean(candidate):
        return not any(r in candidate.lower() for r in refs)

    if clean(url):
        return url
    public = "/shop/%s" % template.env["ir.http"]._slug(
        (template.id, template.seo_name or template.name))
    return public if clean(public) else "/shop/%d" % template.id


def _variant_url(template_url, variant, visible_pavs):
    """The variant URL built the way Odoo builds it, from the values this
    export shows only (a hidden attribute's name and value never reach the
    URL). 18/20: Odoo 18 uses #attribute_values=<ids>; 20 uses query slugs."""
    pavs = variant.product_template_attribute_value_ids.product_attribute_value_id.filtered(
        lambda pav: pav.id in visible_pavs)
    if not pavs:
        return template_url
    slug = variant.env["ir.http"]._slug
    params = {slug(pav.attribute_id): slug(pav) for pav in pavs}
    return urlparse(template_url)._replace(query=urlencode(params)).geturl()


def _rating(template):
    """Approved reviews only. Approval exists only when reza_product_reviews
    is installed (rating.rating.is_approved, and its _rating_domain makes
    rating_count / rating_avg approved-only). Without it there is no approval
    decision, so nothing is exported."""
    if "is_approved" not in template.env["rating.rating"]._fields:
        return None
    count = template.rating_count
    if not count:
        return None
    return {"avg": round(template.rating_avg, 2), "count": count}


def website_payload(website):
    base = website.domain or ""
    if base and not base.startswith("http"):
        base = "https://" + base
    return {
        "id": website.id,
        "name": website.name,
        "domain": base or None,
        "currency": website.currency_id.name,
        "lang": website.default_lang_id.code,
        "prices_include_tax": _website_prices_include_tax(website),
        "products_per_page": website.shop_ppg,
        "logo_url": "/web/image/website/%d/logo" % website.id,
    }


def _public_categories(site):
    """Categories the public user can read on this website (Odoo 20's access
    rule requires published products), in shop order. Bounded."""
    categories = site.env["product.public.category"].search(
        Domain(site.website_domain()), order="sequence, id", limit=MAX_META_ROWS + 1)
    if len(categories) > MAX_META_ROWS:
        raise PageTooLarge("categories", MAX_META_ROWS)
    return categories


def _with_image(env, records, field):
    """Ids of `records` that hold an image in `field`, in one query.

    Image fields are attachment-backed on 18 and 20, so the attachment table
    answers "has an image" without loading a single image into memory.
    """
    if not records:
        return set()
    rows = env["ir.attachment"].sudo().search_read([
        ("res_model", "=", records._name),
        ("res_field", "=", field),
        ("res_id", "in", records.ids),
    ], ["res_id"])
    return {r["res_id"] for r in rows}


def meta(site):
    domain = product_domain(site)
    Templates = _public_templates(site)
    categories = _public_categories(site)
    allowed = set(categories.ids)
    categ_sudo = categories.sudo()
    categ_images = _with_image(site.env, categ_sudo, "image_512")
    brand_rows = Templates._read_group(domain, ["feed_brand_id"], [], limit=MAX_META_ROWS + 1)
    if len(brand_rows) > MAX_META_ROWS:
        raise PageTooLarge("brands", MAX_META_ROWS)
    brands = site.env["product.data.feed.brand"].sudo().browse(
        [b.id for (b,) in brand_rows if b]).sorted(lambda b: (b.name or "", b.id))
    slugify = site.env["ir.http"]._slugify
    rows = []
    for c in categ_sudo:
        # A parent the public user cannot see on this site is not named, and
        # a URL built from such an ancestry is not given either.
        ancestors_ok = all(a.id in allowed for a in c.parents_and_self)
        rows.append({
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id.id if c.parent_id.id in allowed else None,
            "sequence": c.sequence,
            "url": _category_url(c) if ancestors_ok else None,
            "meta_title": c.website_meta_title or None,
            "meta_description": c.website_meta_description or None,
            "image_url": site.image_url(c, "image_512") if c.id in categ_images else None,
        })
    return {
        "contract": CONTRACT,
        "generated_at": _iso(fields.Datetime.now()),
        "website": website_payload(site),
        "categories": rows,
        "brands": [{
            "id": b.id,
            "name": b.name,
            "slug": slugify(b.name or "") or str(b.id),
        } for b in brands],
        "product_count": Templates.search_count(domain),
        # The shop's default order (website.shop_default_sort), as Odoo spells
        # it: "<sort field> <asc|desc>"; products carry the keys in "sort".
        "default_sort": site.shop_default_sort,
        **_content_meta(site),
    }


def _content_meta(site):
    from . import content  # content imports this module
    return content.meta_fields(site)


def parse_paging(page, limit):
    """(page, limit) as ints, or None when either is not a plain positive
    integer within bounds. limit above MAX_LIMIT is capped, as the contract
    says; page above MAX_PAGE is refused."""
    page = "1" if page is None else page
    limit = str(DEFAULT_LIMIT) if limit is None else limit
    if not isinstance(page, str) or not isinstance(limit, str):
        return None
    if not _DIGITS.fullmatch(page) or not _DIGITS.fullmatch(limit):
        return None
    page, limit = int(page), int(limit)
    if page < 1 or limit < 1 or page > MAX_PAGE:
        return None
    return page, min(limit, MAX_LIMIT)


def products_page(site, page, limit, pricing):
    Templates = _public_templates(site)
    domain = product_domain(site)
    total = Templates.search_count(domain)
    offset = (page - 1) * limit
    if offset >= total:
        ids = []  # past the end: no OFFSET query at all
    else:
        ids = Templates.search(domain, order="id", offset=offset, limit=limit).ids
    if ids:
        # Counting stops at the bound: an oversized page costs no more to
        # refuse than a page exactly at the bound.
        variant_count = site.env["product.product"].sudo().search_count(
            [("product_tmpl_id", "in", ids)], limit=MAX_VARIANTS_PER_PAGE + 1)
        if variant_count > MAX_VARIANTS_PER_PAGE:
            raise PageTooLarge("variants", MAX_VARIANTS_PER_PAGE)
    has_more = offset + len(ids) < total
    products = _serialize(site, _sudo_templates(site, ids), pricing)
    if products:
        # Name order depends on the database collation (case, accents), which
        # the storefront cannot reproduce from the name text. The database
        # ranks it instead, with the shop's own order spec, over the whole set.
        rank = name_ranks(site, domain, [row["id"] for row in products])
        for row in products:
            row["sort"]["name_rank"] = rank[row["id"]]
    return {
        "contract": CONTRACT,
        "page": page,
        "limit": limit,
        "product_count": total,
        "next_page": page + 1 if has_more else None,
        "products": products,
    }


def _serialize(site, templates, pricing):
    if not templates:
        return []
    env = site.env
    allowed_categ = set(_public_categories(site).ids)
    ribbons = _ribbons(site, templates, pricing)
    all_variants = templates.product_variant_ids
    # _get_combination_info reads display_name one variant at a time under
    # display_default_code=False, so each call would compute it alone (the
    # d3_website_product_extended override makes that ~2.6 ms each). One
    # batched read in the same context fills the cache those calls hit.
    all_variants.with_context(display_default_code=False).mapped("display_name")
    # Same idea for the stock figure: website_sale_stock reads free_qty one
    # variant at a time with warehouse_id = the website's warehouse (four
    # read_groups each). Computing it once for the page fills that cache.
    # Values still come from Odoo's own call below; a context mismatch here
    # only loses the speed-up, never changes a figure.
    all_variants.sudo().with_context(
        warehouse_id=site.warehouse_id.id).mapped("free_qty")
    extras = templates.product_template_image_ids
    tmpl_images = _with_image(env, templates, "image_1920")
    variant_images = _with_image(env, all_variants, "image_variant_1920")
    extra_images = _with_image(env, extras, "image_1920")
    out = []
    for template in templates:
        variants = template.product_variant_ids
        variant_ptavs = variants.product_template_attribute_value_ids
        name = template.name
        url = _template_url(template)
        images = []
        # _get_images() is the website carousel's own list (18 and 20 build
        # it differently: 20 copies the main image into product.image).
        for record in template._get_images():
            has_image = (extra_images if record._name == "product.image" else tmpl_images)
            if record.id in has_image:
                images.append({
                    "url": site.image_url(record, "image_1920"),
                    "alt": record.name or name,
                })
        attributes = []
        exported_values = set()
        for line in template.attribute_line_ids:
            attr = line.attribute_id
            if attr.visibility != "visible":
                continue  # hidden on the shop
            # A value counts when an active variant carries it (a value whose
            # only variants are archived is not sellable), or when it belongs
            # to a no-variant attribute (chosen at order time).
            values = line.product_template_value_ids.filtered(
                lambda ptav, attr=attr: ptav.ptav_active and (
                    attr.create_variant == "no_variant" or ptav in variant_ptavs))
            if not values:
                continue
            exported_values.update(values.product_attribute_value_id.ids)
            attributes.append({
                "id": attr.id,
                "name": attr.name,
                "display_type": attr.display_type,
                "show_in_website": True,
                "values": [{
                    "id": ptav.product_attribute_value_id.id,
                    "name": ptav.product_attribute_value_id.name,
                    "html_color": ptav.product_attribute_value_id.html_color or None,
                } for ptav in values],
            })
        variant_rows = []
        prices = []
        for variant in variants:
            info = _combination_info(template, variant, pricing)
            hidden = _price_hidden(info)
            price = None if hidden else info["price"]
            if price is not None:
                prices.append(price)
            allow = _effective_allow_out_of_stock(template, info)
            qty = _variant_qty(site, variant, info)
            if variant.id in variant_images:
                image_url = site.image_url(variant, "image_1920")
            elif template.id in tmpl_images:
                image_url = site.image_url(template, "image_1920")
            else:
                image_url = None
            variant_rows.append({
                "id": variant.id,
                "default_code": variant.default_code or None,
                "barcode": variant.barcode or None,
                "value_ids": [v for v in variant.product_template_attribute_value_ids
                              .product_attribute_value_id.ids if v in exported_values],
                "image_url": image_url,
                "price": price,
                "compare_price": _strike_price(info),
                "currency": info["currency"].name,
                "available_qty_band": _band(template, allow, qty),
                "available_qty": qty,
                "allow_out_of_stock_order": allow,
                "url": _variant_url(url, variant, exported_values),
            })
        # Two variants that differ only in values this export hides share the
        # same visible selector: a selector URL would open one of them for
        # both, so each of them gets the product URL instead.
        selectors = [tuple(sorted(row["value_ids"])) for row in variant_rows]
        for row, selector in zip(variant_rows, selectors):
            if selectors.count(selector) > 1:
                row["url"] = url
        ribbon = ribbons.get(template.id)
        out.append({
            "id": template.id,
            "name": name,
            "url": url,
            "write_date": _iso(template.write_date),
            "description_html": _str_or_none(
                template._seo_body_override(site) or template.description_ecommerce),
            "description_sale": template.description_sale or None,
            "meta_title": template._seo_for_website(site, "website_meta_title") or None,
            "meta_description": template._seo_for_website(
                site, "website_meta_description") or None,
            "meta_keywords": template.website_meta_keywords or None,
            "category_ids": [c for c in template.public_categ_ids.ids if c in allowed_categ],
            "brand_id": template.feed_brand_id.id or None,
            "ribbon": {
                "name": ribbon.name,
                "bg": ribbon.bg_color,
                "text": ribbon.text_color,
            } if ribbon else None,
            "images": images,
            "attributes": attributes,
            "variants": variant_rows,
            "price_min": min(prices) if prices else None,
            "price_max": max(prices) if prices else None,
            "rating": _rating(template),
            "sort": _sort_keys(
                template, not variant_rows or any(r["price"] is None for r in variant_rows)),
        })
    return out
