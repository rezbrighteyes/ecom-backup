import json
import logging

from markupsafe import Markup
from odoo import fields, models
from odoo.http import request

_logger = logging.getLogger(__name__)


MAX_TITLE = 60


class Website(models.Model):
    _inherit = 'website'

    seo_title_suffix = fields.Char(
        string='SEO Title Suffix',
        help="Appended to page titles on this website only, e.g. ' | Sunglass Superstore'. "
             "Leave empty for no suffix. Every other SEO setting in this module is a global "
             "config parameter shared by all websites; this one is not, because a shared "
             "product must be able to name the site a visitor is actually on.",
    )

    def _get_seo_param(self, key, default=''):
        try:
            return self.env['ir.config_parameter'].sudo().get_param(
                'rezads_seo.%s' % key, default
            )
        except Exception:
            return default

    def _seo_feature_enabled(self, feature):
        return self._get_seo_param('enable_%s' % feature, 'True') == 'True'

    def _seo_page_number(self):
        """Which page of a paginated listing this request is, or 0.

        Odoo paginates as /shop/category/<slug>/page/3.
        """
        if not request or not getattr(request, 'httprequest', None):
            return 0
        path = (request.httprequest.path or '').rstrip('/')
        if '/page/' not in path:
            return 0
        tail = path.rsplit('/page/', 1)[-1]
        return int(tail) if tail.isdigit() else 0

    def _seo_paginated_title(self, seo_object):
        """Title for page 2 and beyond, or False when the page is not paginated.

        Every paginated page carried the SAME title as page one and canonicalised
        to itself, so Google saw a run of identical pages each claiming to be
        "Wrap Polarised Sunglasses" and picked between them arbitrarily. It picked
        page 2: 186 impressions at position 1.5, one click, while page one — the
        page that should rank — went unshown.

        Numbering the title is the smallest fix that resolves the ambiguity. The
        pages stay indexed and keep their self-canonical, which is what Google
        asks for; they just stop claiming to be each other.
        """
        page = self._seo_page_number()
        if page < 2:
            return False

        base = ''
        if seo_object:
            fields = getattr(seo_object, '_fields', {})
            if 'website_meta_title' in fields and seo_object.website_meta_title:
                base = seo_object.website_meta_title
            elif 'name' in fields and seo_object.name:
                base = '%s | %s' % (seo_object.name, self.name or '')
        if not base:
            base = self.name or ''
        return '%s | Page %s' % (base.strip(' |'), page)

    def _seo_site_title(self, seo_object):
        """The page title for THIS website, including its own suffix.

        website_meta_title is stored once on the record and Odoo scopes it by language, never by
        website. 785 live products in this database are carried by two or more storefronts, so a
        title generated with one site's suffix baked in is wrong on every other site showing the
        same product -- "Mangrove Jacks Adder C1 | Mangrove Jacks" read on Sunglass Superstore.

        The stored title therefore stays site-neutral and the suffix is applied here, at render
        time, from the website actually being served.

        Returns False when nothing would change, so the caller falls through to Odoo's own
        title logic untouched.
        """
        self.ensure_one()
        # The suffix is used verbatim, never stripped: the leading space in " | Sunglass
        # Superstore" is the separator, and trimming it renders "Sunglasses| Sunglass
        # Superstore". Only its emptiness is tested.
        suffix = self.seo_title_suffix or ''
        base = self._seo_paginated_title(seo_object)

        if not suffix.strip():
            return base

        if not base:
            fields_ = getattr(seo_object, '_fields', {}) if seo_object else {}
            if 'website_meta_title' in fields_ and seo_object.website_meta_title:
                base = seo_object.website_meta_title
            elif 'name' in fields_ and seo_object.name:
                base = seo_object.name
        base = (base or '').strip()
        if not base:
            return False

        if base.casefold().endswith(suffix.casefold()):
            return False

        # Trim the core rather than the suffix: a title cut mid-way through the site name reads
        # like a bug, and the product words are the ones worth losing last.
        room = MAX_TITLE - len(suffix)
        if room < 12:
            # The suffix would leave nothing useful. Publishing the product name alone beats
            # publishing the site name alone.
            return False
        if len(base) > room:
            base = base[:room].rsplit(' ', 1)[0].rstrip(' |-,')
        return '%s%s' % (base, suffix)

    def _seo_base_url(self):
        """This website's own public origin, never another site's.

        website.domain is blank on several records in this database, and Odoo
        then falls back to the shared base URL — which is why three storefronts
        emit ecomsuperstore.com.au as their canonical. Schema must not repeat
        that: an empty domain yields relative URLs rather than a URL belonging
        to a different business.
        """
        self.ensure_one()
        domain = (self.domain or '').strip()
        if not domain:
            return ''
        if not domain.startswith('http'):
            domain = 'https://%s' % domain
        return domain.rstrip('/')

    def _seo_canonical_domain(self):
        """The origin this website's canonical tags must name — never a sibling's.

        Odoo builds the canonical from website.get_base_url(), which falls back
        to the shared web.base.url parameter when website.domain is blank.
        Three storefronts here have it blank, so every page on Sunglass
        Superstore, Rockos and Youreyesonly declares ecomsuperstore.com.au as
        its real address — their 404 pages included. Sunglass Superstore is
        down to 3 organic visits and 5 keywords as a result.

        Every storefront in this estate is its own business with its own
        pricing and range and has to rank on its own, so the fallback is the
        host actually being served rather than a sibling's domain. A newly
        created website is then correct before anyone remembers to fill the
        field in, which is the point: this must not need re-fixing per site.
        """
        self.ensure_one()
        own = self._seo_base_url()
        if own:
            return own
        try:
            if request and request.httprequest:
                return request.httprequest.host_url.rstrip('/')
        except Exception:
            pass
        return (self.get_base_url() or '').rstrip('/')

    def _seo_social_profiles(self):
        """Social URLs configured on the website, for Organization.sameAs."""
        self.ensure_one()
        fields = (
            'social_facebook', 'social_instagram', 'social_twitter',
            'social_youtube', 'social_linkedin', 'social_tiktok',
        )
        urls = []
        for name in fields:
            value = (getattr(self, name, '') or '').strip()
            if value and value.startswith('http'):
                urls.append(value)
        return urls

    def get_site_jsonld(self):
        """Organization and WebSite for every page on this storefront.

        The estate emitted no site-level structured data at all: no
        Organization, no WebSite, no logo, no sameAs. Product pages carried
        Product and BreadcrumbList and nothing else did, which left Google
        without a machine-readable statement of who runs the site.

        Emitted as a @graph so both nodes ship in one script tag and can
        reference each other by @id.
        """
        self.ensure_one()
        if not self._seo_feature_enabled('site_schema'):
            return Markup('')
        try:
            base = self._seo_canonical_domain()
            org_id = '%s/#organization' % base if base else '#organization'
            site_id = '%s/#website' % base if base else '#website'

            organization = {
                '@type': 'Organization',
                '@id': org_id,
                'name': self.name or '',
                'url': '%s/' % base if base else '/',
            }

            logo_path = '/web/image/website/%s/logo' % self.id
            organization['logo'] = {
                '@type': 'ImageObject',
                'url': '%s%s' % (base, logo_path) if base else logo_path,
            }

            same_as = self._seo_social_profiles()
            if same_as:
                organization['sameAs'] = same_as

            company = self.company_id
            phone = (getattr(company, 'phone', '') or '').strip()
            if phone:
                organization['contactPoint'] = {
                    '@type': 'ContactPoint',
                    'telephone': phone,
                    'contactType': 'customer service',
                    'areaServed': 'AU',
                }

            website_node = {
                '@type': 'WebSite',
                '@id': site_id,
                'name': self.name or '',
                'url': '%s/' % base if base else '/',
                'publisher': {'@id': org_id},
            }
            if base:
                website_node['potentialAction'] = {
                    '@type': 'SearchAction',
                    'target': {
                        '@type': 'EntryPoint',
                        'urlTemplate': '%s/shop?search={search_term_string}' % base,
                    },
                    'query-input': 'required name=search_term_string',
                }

            data = {
                '@context': 'https://schema.org/',
                '@graph': [organization, website_node],
            }
            return Markup(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            _logger.error('Site JSON-LD error for website %s: %s', self.id, e)
            return Markup('')
