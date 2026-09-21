import re
import json
import logging
import unicodedata
from datetime import date, timedelta
from markupsafe import Markup
from odoo import fields, api, models
from odoo.http import request

_logger = logging.getLogger(__name__)

STOP_WORDS = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}


def _make_slug(name):
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = re.sub(r'[^\w\s-]', '', name).strip().lower()
    words = [w for w in name.split() if w not in STOP_WORDS]
    return re.sub(r'[\s_-]+', '-', ' '.join(words))


def _plain_slug(text):
    """Slugify the way Odoo's router does: keep every word, drop punctuation.

    Deliberately not _make_slug — that strips stop words, which is right for a
    hand-built seo_name and wrong for reproducing a URL Odoo already serves.
    """
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[\s_-]+', '-', text)


def _slug_record(record):
    """Odoo's own '<slug>-<id>' identifier for a record.

    The helper moved between versions — ir.http._slug on 17+, a module-level
    slug() in http_routing before that — so both are tried before falling back
    to building it here. Odoo slugifies display_name, which is why a child
    category carries its parent's words (Sunglasses / Wrap -> sunglasses-wrap).
    """
    if not record:
        return ''
    try:
        return record.env['ir.http']._slug(record)
    except Exception:
        pass
    try:
        from odoo.addons.http_routing.models.ir_http import slug
        return slug(record)
    except Exception:
        pass
    label = getattr(record, 'display_name', None) or getattr(record, 'name', '') or ''
    return '%s-%s' % (_plain_slug(label), record.id)


def _extract_seo_description(html, max_chars=160):
    if not html:
        return None
    text = re.sub(r'</(h[1-6]|p|div|li)>', '. ', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\.\s*\.', '.', text)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) < 30:
        return None
    sentences = re.split(r'(?<=[.!?])\s+', text)
    result = ""
    for sentence in sentences:
        if not result and len(sentence) < 20:
            continue
        candidate = (result + " " + sentence).strip() if result else sentence
        if len(candidate) <= max_chars:
            result = candidate
        else:
            break
    if len(result) >= 50:
        return result
    trimmed = text[:max_chars]
    last_space = trimmed.rfind(' ')
    return (trimmed[:last_space] + '...').strip() if last_space > 0 else trimmed


def _strip_html(html):
    if not html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ---------------------------------------------------------------------------
# Meta-title construction
#
# GSC demand for these catalogues is brand + category ("mangrove jacks
# sunglasses", "fish thongs") — never a model code or a colourway. So the title
# budget (~60 chars, Google's display cut) is spent in value order:
#
#     brand  ->  model  ->  Polarised  ->  category noun
#
# and the colourway (Black / Smoke ...) is dropped: it carries no search value
# and already sits in the H1. The old generator did record.name[:45] — a hard
# character cut that severed words ("Polaris" out of "Polarised"), left dangling
# separators ("Black / "), then spent 13 chars on " | Buy Online" that nobody
# searches. Everything below replaces that. The functions are pure so they can
# be verified without a database.
# ---------------------------------------------------------------------------
MAX_META_TITLE = 60

# product.website.seo stores an override under its own short column name, not under
# the product.template field name the callers pass to _seo_for_website(). Indexing the
# override record with the template name raises KeyError, so map it first.
_SEO_OVERRIDE_FIELD = {
    'website_meta_title': 'meta_title',
    'website_meta_description': 'meta_description',
    'description_ecommerce': 'description_ecommerce',
}
_TITLE_SEPARATORS = ' -/&,+|'

# Redundant phrasing shortened before anything is ever cut. Order matters.
_TITLE_COMPRESSIONS = [
    (' Polarised Lenses', ' Polarised'),
    (' Revo Mirror ', ' Revo '),
    (' Mirror Polarised', ' Polarised'),
    (' Matte Crystal ', ' Crystal '),
    (' w Matte ', ' / '),
    (' w ', ' / '),
]

# Category noun injected when the name/categories imply it and it is not already
# present. First match wins, so more specific needles come first. This is a
# curated map on purpose: an unrecognised category adds NO noun rather than
# appending a raw, possibly noisy category label.
_CATEGORY_NOUNS = [
    ('sunglass', 'Sunglasses'),
    ('thong', 'Thongs'),
    ('sandal', 'Thongs'),
    ('lure', 'Fishing'),
    ('tackle', 'Fishing'),
    ('fishing', 'Fishing'),
    ('visor', 'Hat'),
    ('cap', 'Hat'),
    ('hat', 'Hat'),
    ('reading glass', 'Reading Glasses'),
    ('optical', 'Glasses'),
    ('watch', 'Watch'),
]

# Filler that must never be the last word of a trimmed title.
_TITLE_TAIL_FILLER = {'w', 'with', 'and', 'the', 'for', 'matte', 'gloss', 'crystal'}

# Names that must NOT inherit a category noun. An accessory sits under its
# parent's category (a cord under Sunglasses), so category-derived noun
# injection would wrongly label "Neoprene Cord" as "Sunglasses". A name already
# carrying '|'-delimited spec fields reads badly with a noun tacked on the end.
_ACCESSORY_TERMS = {
    'cord', 'strap', 'retainer', 'lanyard', 'leash', 'case', 'pouch', 'bag',
    'cloth', 'cleaning', 'kit', 'spare', 'screw', 'hinge', 'float', 'floating',
}


def _noun_suppressed(name):
    """True when a category noun must not be appended to this name."""
    if '|' in name:
        return True
    return any(t in _ACCESSORY_TERMS for t in re.findall(r'[a-z]+', name.lower()))


def _title_spaces(text):
    return re.sub(r'\s+', ' ', text or '').strip()


def _title_rstrip(text):
    return (text or '').rstrip(_TITLE_SEPARATORS).strip()


def _title_word_trim(text, limit):
    """Trim to `limit` on a word boundary, then drop trailing separators/filler."""
    text = _title_spaces(text)
    if len(text) <= limit:
        return _title_rstrip(text)
    cut = text[:limit]
    if ' ' in cut:
        cut = cut[:cut.rindex(' ')]
    cut = _title_rstrip(cut)
    while cut and cut.split()[-1].lower() in _TITLE_TAIL_FILLER:
        cut = _title_rstrip(cut[:cut.rindex(' ')]) if ' ' in cut else ''
    return cut


def _category_noun(candidates):
    """First curated noun implied by any candidate string, else ''."""
    hay = ' '.join(c for c in candidates if c).lower()
    for needle, noun in _CATEGORY_NOUNS:
        if needle in hay:
            return noun
    return ''


def _strip_colourway(core):
    """Remove the colourway that sits between the model code and 'Polarised'.

    MJ names read '<brand> <model> <code> <colourway> Polarised ...'. The model
    code is a short letter+digit token (C1, C8, RB3025). Everything from the
    first such code to 'Polarised' is the colourway and is dropped. When no code
    is present the colourway boundary is unknown, so only an explicit '<x> / <y>'
    colour segment is removed; otherwise the name is left intact rather than
    guessed at.
    """
    m = re.search(r'\bpolaris\w*\b', core, re.IGNORECASE)
    if not m:
        return core
    head, tail = core[:m.start()], core[m.start():]
    # The LAST code before 'Polarised', not the first. A kids name carries two -
    # the range code and the colour code, as in 'Kids MJK059 C4' - and taking the
    # first treated 'C4' as colourway, collapsing every colourway of a range onto
    # one title. 43 of 440 products shared 13 titles because of it.
    codes = list(re.finditer(r'\b[A-Za-z]{1,4}\d{1,4}\b', head))
    if codes:
        head = head[:codes[-1].end()]
    else:
        slash = head.find(' / ')
        if slash != -1:
            head = head[:slash]
            head = head[:head.rindex(' ')] if ' ' in head else head
    return _title_spaces('%s %s' % (_title_rstrip(head), tail))


def _fit_meta_title(core, category_noun, limit):
    """Fit an over-long title, protecting Polarised and the category noun.

    Colourway is already gone; what remains long is a wordy brand+model. Trim the
    body (brand+model) from the right, reserving room for Polarised and the noun.
    """
    noun = category_noun if (category_noun and core.lower().endswith(category_noun.lower())) else ''
    body = core[:len(core) - len(noun)].strip() if noun else core
    pol = ''
    mpol = re.search(r'\bpolaris\w*\b', body, re.IGNORECASE)
    if mpol:
        pol = body[mpol.start():mpol.end()]
        body = _title_spaces(body[:mpol.start()] + ' ' + body[mpol.end():])
    reserve = len(pol) + (1 if pol else 0) + (len(noun) + 1 if noun else 0)
    body = _title_word_trim(body, max(0, limit - reserve))
    return _title_spaces(' '.join(p for p in (body, pol, noun) if p))


def _compose_meta_title(name, category_noun='', limit=MAX_META_TITLE):
    """Build the SEO title body from a product name. Pure; no ORM."""
    core = _title_spaces(name)
    if not core:
        return ''
    for phrase, replacement in _TITLE_COMPRESSIONS:
        if phrase in core:
            core = _title_spaces(core.replace(phrase, replacement))
    if 'polaris' in core.lower():
        core = _strip_colourway(core)
    core = _title_rstrip(core)
    if category_noun and category_noun.lower() not in core.lower():
        core = '%s %s' % (core, category_noun)
    core = _title_spaces(core)
    if len(core) <= limit:
        return core
    return _fit_meta_title(core, category_noun, limit)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_seo_param(self, key, default=''):
        try:
            return self.env['ir.config_parameter'].sudo().get_param(
                'rezads_seo.%s' % key, default
            )
        except Exception:
            return default

    def _seo_feature_enabled(self, feature):
        return self._get_seo_param('enable_%s' % feature, 'True') == 'True'

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._set_seo_defaults()
        return records

    def write(self, vals):
        old_slugs = {}
        if 'name' in vals and self._seo_feature_enabled('redirects'):
            for record in self:
                if record.seo_name:
                    old_slugs[record.id] = record.seo_name

        res = super().write(vals)

        if any(f in vals for f in ('name', 'description_ecommerce', 'feed_brand_id', 'tag_ids')):
            self._set_seo_defaults(
                name_changed='name' in vals,
                desc_changed='description_ecommerce' in vals,
            )

        if old_slugs:
            for record in self:
                old_slug = old_slugs.get(record.id)
                if old_slug and record.seo_name and old_slug != record.seo_name:
                    record._create_seo_redirect(old_slug)

        return res

    def _create_seo_redirect(self, old_slug):
        self.ensure_one()
        if not self._seo_feature_enabled('redirects'):
            return
        try:
            # Both sides need the record id the router matches on. Without it
            # the rewrite points from a URL that never existed to one that 404s.
            old_url = '/shop/%s-%s' % (old_slug, self.id)
            new_url = self._canonical_path()
            existing = self.env['website.rewrite'].sudo().search([
                ('url_from', '=', old_url),
            ], limit=1)
            if not existing:
                self.env['website.rewrite'].sudo().create({
                    'name': 'SEO Redirect: %s' % self.name,
                    'url_from': old_url,
                    'url_to': new_url,
                    'redirect_type': '301',
                })
                _logger.info('301 redirect created: %s -> %s', old_url, new_url)
        except Exception as e:
            _logger.warning('Could not create 301 redirect for %s: %s', self.name, e)

    def _build_meta_title(self):
        """Shared SEO-title builder. The single source of truth for both the
        automatic generation below and the regenerate wizard, so the two can
        never drift apart or re-break the catalogue against each other.

        The category noun comes from the website categories or the name; the
        colourway is dropped; 'Polarised' is protected; the title is trimmed on
        a word boundary to 60 chars. The config template is honoured for sites
        that set a custom one, but is substituted with str.replace rather than
        %-formatting: a '%' in a product name would otherwise raise ValueError
        and silently fall back to the old suffix.
        """
        self.ensure_one()
        name = self.name or ''
        candidates = []
        if 'public_categ_ids' in self._fields and self.public_categ_ids:
            candidates += self.public_categ_ids.mapped('name')
        if self.categ_id:
            candidates.append(self.categ_id.name)
        candidates.append(name)
        noun = _category_noun(candidates)
        if noun and _noun_suppressed(name):
            # Accessory or spec-style name — do not inherit the parent
            # category's noun (a cord is not "Sunglasses").
            noun = ''
        core = _compose_meta_title(name, noun)
        # Default is now '%(name)s' (no suffix). " | Buy Online" earned nothing
        # in search and ate 13 chars; a site wanting a suffix sets the template.
        template = self._get_seo_param('meta_title_template', '%(name)s')
        if template and template.strip() not in ('', '%(name)s'):
            title = template.replace('%(name)s', core)
        else:
            title = core
        return _title_word_trim(title, MAX_META_TITLE)

    website_seo_ids = fields.One2many(
        'product.website.seo', 'product_tmpl_id', string='Per-website SEO')

    # The template-name-to-override-column mapping is _SEO_OVERRIDE_FIELD, defined at module
    # level beside MAX_META_TITLE. Two copies of it would drift the first time a field is added.

    def _seo_for_website(self, website=None, field=None):
        """The value this website should show, falling back to the shared field.

        Resolution is override -> shared -> empty, and it never skips a step. A missing override
        is not an instruction to publish nothing; it means "the shared wording is fine here",
        which is true for most of the catalogue.
        """
        self.ensure_one()
        if website is None:
            website = self.env['website'].get_current_website()
        shared = self[field] if field in self._fields else False
        if not website:
            return shared
        override_field = _SEO_OVERRIDE_FIELD.get(field)
        if not override_field:
            # A field with no override column cannot be overridden, and guessing a column
            # name here is how the KeyError this map exists to prevent comes back.
            return shared
        override = self.website_seo_ids.filtered(lambda r: r.website_id == website)[:1]
        if not override:
            return shared
        if override_field not in override._fields:
            return shared
        return override[override_field] or shared

    def _seo_body_override(self, website=None):
        """This website's own body copy, or False when it has none.

        Deliberately returns False rather than the shared description, because the caller is a
        product page template that still renders ``description_ecommerce`` through an editable
        ``t-field``. Returning the shared value here would replace an editable snippet with a
        read-only one on every product in the catalogue, and in-place editing on the front end
        is how this copy has always been written.

        So an override takes the page over only where one exists, and everywhere else the page
        behaves exactly as it did before this module touched it.
        """
        self.ensure_one()
        if website is None:
            website = self.env['website']
            if request and getattr(request, 'httprequest', None):
                website = self.env['website'].get_current_website()
        if not website:
            return False
        override = self.website_seo_ids.filtered(lambda r: r.website_id == website)[:1]
        return override.description_ecommerce or False

    def _set_seo_defaults(self, name_changed=False, desc_changed=False):
        for record in self:
            updates = {}

            if record._seo_feature_enabled('auto_title'):
                if not record.website_meta_title or name_changed:
                    updates['website_meta_title'] = record._build_meta_title()

            if record._seo_feature_enabled('auto_slug'):
                if not record.seo_name or name_changed:
                    updates['seo_name'] = _make_slug(record.name)

            if record._seo_feature_enabled('auto_description'):
                if not record.website_meta_description or desc_changed:
                    desc = _extract_seo_description(record.description_ecommerce)
                    if desc:
                        updates['website_meta_description'] = desc

            if record._seo_feature_enabled('auto_keywords'):
                if not record.website_meta_keywords or name_changed:
                    keywords = []
                    if getattr(record, 'feed_brand_id', False) and record.feed_brand_id:
                        keywords.append(record.feed_brand_id.name)
                    if record.categ_id:
                        keywords.append(record.categ_id.name)
                    if getattr(record, 'tag_ids', False):
                        keywords += record.tag_ids.mapped('name')
                    keywords.append(record.name)
                    updates['website_meta_keywords'] = ', '.join(keywords)

            if updates:
                super(ProductTemplate, record).write(updates)

    def _is_in_stock(self):
        self.ensure_one()
        product_sudo = self.sudo()
        if getattr(product_sudo, 'allow_out_of_stock_order', False):
            return True
        variant_ids = product_sudo.product_variant_ids.ids
        if not variant_ids:
            return False
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', 'in', variant_ids),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
        ])
        return sum(quants.mapped('quantity')) > 0

    def _get_domain(self):
        try:
            website = self.env['website'].get_current_website()
            domain = website.domain or ''
            if domain and not domain.startswith('http'):
                domain = 'https://%s' % domain
            return domain.rstrip('/')
        except Exception:
            return ''

    def _get_currency_code(self):
        try:
            website = self.env['website'].get_current_website()
            if website.currency_id:
                return website.currency_id.name
        except Exception:
            pass
        return 'AUD'

    def _website_offer_price(self):
        """The price the storefront actually charges, not the list price.

        The product page renders combination_info['price'] — the pricelist
        applied — while this schema used list_price. Every discounted product
        therefore advertised a price the customer would never be charged
        ($69.99 in JSON-LD against $57.74 on the page). Merchant Center reads
        that as a price mismatch and can disapprove the item, and where a rich
        result does show it quotes the higher number.

        Falls back to list_price only when combination info is unavailable
        (no variant, no website context), which is the old behaviour.
        """
        self.ensure_one()
        try:
            info = self._get_combination_info(only_template=True)
            price = info.get('price')
            if price is not None:
                return float(price)
        except Exception as e:
            _logger.warning(
                'Website price unavailable for product %s, using list_price: %s',
                self.id, e,
            )
        return float(self.list_price or 0)

    def _get_brand_name(self, website_name=''):
        self.ensure_one()
        if getattr(self, 'feed_brand_id', False) and self.feed_brand_id:
            return self.feed_brand_id.name
        default_brand = self._get_seo_param('default_brand', '')
        if default_brand:
            return default_brand
        return website_name

    def _canonical_path(self):
        """The path Odoo actually serves for this product: /shop/<slug>-<id>.

        seo_name on its own is not a URL. The router appends the record id and
        matches on it, so /shop/<seo_name> returns 404. website_url is the same
        value the canonical tag uses, so schema and canonical cannot disagree.
        """
        self.ensure_one()
        try:
            url = self.website_url
            if url:
                return url
        except Exception:
            pass
        return '/shop/%s' % _slug_record(self)

    def _breadcrumb_categories(self):
        """Public-category ancestors to show, scoped to the current website.

        public_categ_ids is shared across the whole estate and each category
        belongs to one website, so picking without filtering emits another
        site's category URL — which 404s on this domain. Returns root first.

        Filtering the leaf is not enough. Category trees cross websites in this
        database: 'Ride-Ons' (id 108) belongs to WhatYouNeed but its parent
        'Toys' (id 88) belongs to ecomsuperstore, so walking parent_id from a
        correctly-scoped leaf still emitted /shop/category/toys-88 — a 404 on
        whatyouneed.com.au, inside a BreadcrumbList Google reads. The walk now
        stops at the first ancestor that belongs to another website, which
        yields a shorter but resolvable trail. Reparenting 108 under a
        WhatYouNeed root is the data-side half of the fix.
        """
        self.ensure_one()
        cats = self.public_categ_ids
        website_id = False
        try:
            website_id = self.env['website'].get_current_website().id
        except Exception:
            pass

        def _on_this_website(categ):
            """A category with no website is shared and always resolvable."""
            if not website_id:
                return True
            return not categ.website_id or categ.website_id.id == website_id

        if website_id:
            scoped = cats.filtered(_on_this_website)
            if scoped:
                cats = scoped
        if not cats:
            return []

        def _depth(categ):
            depth, node = 0, categ
            while node.parent_id:
                depth += 1
                node = node.parent_id
            return depth

        leaf = sorted(cats, key=lambda c: (-_depth(c), c.id))[0]
        chain, node = [], leaf
        while node and _on_this_website(node):
            chain.insert(0, node)
            node = node.parent_id
        return chain

    def _free_shipping_threshold(self):
        """Order value above which this website ships free, or None.

        Each storefront sets its own threshold, so this reads the per-website
        value where sunglass_superstore_product_page provides it and falls back
        to a configured default. Returns None when no threshold is known, which
        makes the caller omit shippingDetails rather than invent a rate.
        """
        self.ensure_one()
        getter = getattr(self, '_sf_get_shipping_threshold', None)
        if getter:
            try:
                value = getter()
                if value is not None:
                    return float(value)
            except Exception:
                pass
        configured = self._get_seo_param('free_shipping_threshold', '')
        try:
            return float(configured) if configured else None
        except (TypeError, ValueError):
            return None

    def _merchant_policies(self):
        """shippingDetails and hasMerchantReturnPolicy for the Offer.

        Google wants both on a product offer, and their absence is a soft
        warning in Merchant Center. Two rules keep the output honest:

        - shippingDetails is emitted only when this item's own price already
          clears the free-shipping threshold, so 'shippingRate 0' is true for
          buying it alone. Below the threshold the real rate depends on the
          basket and the destination, which is not knowable here, so the
          property is omitted rather than guessed.
        - the return window is a flat site-wide policy, so it is always safe.
        """
        self.ensure_one()
        policies = {}

        threshold = self._free_shipping_threshold()
        if threshold is not None and self._website_offer_price() >= threshold:
            policies['shippingDetails'] = {
                '@type': 'OfferShippingDetails',
                'shippingRate': {
                    '@type': 'MonetaryAmount',
                    'value': '0',
                    'currency': self._get_currency_code(),
                },
                'shippingDestination': {
                    '@type': 'DefinedRegion',
                    'addressCountry': 'AU',
                },
            }

        try:
            return_days = int(self._get_seo_param('return_days', '30'))
        except (TypeError, ValueError):
            return_days = 30
        if return_days > 0:
            policies['hasMerchantReturnPolicy'] = {
                '@type': 'MerchantReturnPolicy',
                'applicableCountry': 'AU',
                'returnPolicyCategory':
                    'https://schema.org/MerchantReturnFiniteReturnWindow',
                'merchantReturnDays': return_days,
                'returnMethod': 'https://schema.org/ReturnByMail',
            }

        return policies

    def _get_gtin13(self):
        """barcode as a GTIN-13, or ''. Google matches offers on gtin, not sku."""
        self.ensure_one()
        code = (self.barcode or '').strip()
        return code if len(code) == 13 and code.isdigit() else ''

    def get_noindex(self):
        self.ensure_one()
        if not self._seo_feature_enabled('noindex'):
            return False
        try:
            if not self.website_published:
                return True
            if not self.sale_ok:
                return True
            if not self.active:
                return True
            return False
        except Exception:
            return False

    def get_breadcrumb_jsonld(self, website_name=''):
        self.ensure_one()
        if not self._seo_feature_enabled('breadcrumbs'):
            return Markup('')
        try:
            domain = self._get_domain()
            items = []
            items.append({
                '@type': 'ListItem',
                'position': 1,
                'name': website_name or 'Home',
                'item': '%s/' % domain if domain else '/',
            })
            items.append({
                '@type': 'ListItem',
                'position': 2,
                'name': 'Shop',
                'item': '%s/shop' % domain if domain else '/shop',
            })
            # categ_id is the internal category and has no storefront page.
            # The public categories do, one per website.
            for categ in self._breadcrumb_categories():
                categ_path = '/shop/category/%s' % _slug_record(categ)
                items.append({
                    '@type': 'ListItem',
                    'position': len(items) + 1,
                    'name': categ.name or '',
                    'item': '%s%s' % (domain, categ_path) if domain else categ_path,
                })
            product_path = self._canonical_path()
            items.append({
                '@type': 'ListItem',
                'position': len(items) + 1,
                'name': self.name or '',
                'item': '%s%s' % (domain, product_path) if domain else product_path,
            })
            data = {
                '@context': 'https://schema.org/',
                '@type': 'BreadcrumbList',
                'itemListElement': items,
            }
            return Markup(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            _logger.error('Breadcrumb JSON-LD error for product %s: %s', self.name, e)
            return Markup('')

    def get_schema_jsonld(self, website_name=''):
        self.ensure_one()
        if not self._seo_feature_enabled('schema'):
            return Markup('')
        try:
            domain = self._get_domain()
            currency = self._get_currency_code()

            availability = (
                'https://schema.org/InStock'
                if self._is_in_stock()
                else 'https://schema.org/OutOfStock'
            )

            image_path = '/web/image/product.template/%s/image_1024' % self.id
            image_url = '%s%s' % (domain, image_path) if domain else image_path

            product_path = self._canonical_path()
            product_url = '%s%s' % (domain, product_path) if domain else product_path

            description = (
                self.description_sale
                or _strip_html(self.description_ecommerce)
                or self.name
                or ''
            )

            valid_until = (date.today() + timedelta(days=30)).isoformat()

            data = {
                '@context': 'https://schema.org/',
                '@type': 'Product',
                'name': self.name or '',
                'description': description,
                'image': image_url,
                'url': product_url,
                'sku': self.default_code or '',
                'brand': {
                    '@type': 'Brand',
                    'name': self._get_brand_name(website_name),
                },
                'offers': {
                    '@type': 'Offer',
                    'url': product_url,
                    'priceCurrency': currency,
                    'price': '%.2f' % self._website_offer_price(),
                    'priceValidUntil': valid_until,
                    'availability': availability,
                    'seller': {
                        '@type': 'Organization',
                        'name': website_name or '',
                    }
                }
            }

            if self._seo_feature_enabled('merchant_policies'):
                data['offers'].update(self._merchant_policies())

            # Google matches an offer on gtin before sku. sku here is whatever
            # sits in default_code, which is not a GTIN on every record.
            gtin13 = self._get_gtin13()
            if gtin13:
                data['gtin13'] = gtin13
                data['offers']['gtin13'] = gtin13

            # Add aggregateRating if approved reviews exist
            try:
                approved = self.env['rating.rating'].sudo().search([
                    ('res_model', '=', 'product.template'),
                    ('res_id', '=', self.id),
                    ('is_approved', '=', True),
                    ('rating', '>=', 1),
                ])
                if approved:
                    avg = sum(approved.mapped('rating')) / len(approved)
                    data['aggregateRating'] = {
                        '@type': 'AggregateRating',
                        'ratingValue': '%.1f' % avg,
                        'reviewCount': len(approved),
                        'bestRating': '5',
                        'worstRating': '1',
                    }
            except Exception:
                pass

            return Markup(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            _logger.error('Schema JSON-LD error for product %s (id=%s): %s', self.name, self.id, e)
            return Markup('{}')