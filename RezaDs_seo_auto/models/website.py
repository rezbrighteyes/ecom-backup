import json
import logging

from markupsafe import Markup
from odoo import models
from odoo.http import request

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = 'website'

    def _get_seo_param(self, key, default=''):
        try:
            return self.env['ir.config_parameter'].sudo().get_param(
                'rezads_seo.%s' % key, default
            )
        except Exception:
            return default

    def _seo_feature_enabled(self, feature):
        return self._get_seo_param('enable_%s' % feature, 'True') == 'True'

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
