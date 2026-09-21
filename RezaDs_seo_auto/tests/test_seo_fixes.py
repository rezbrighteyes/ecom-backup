import json

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestOfferPrice(TransactionCase):
    """The Offer must quote the price the storefront charges.

    The schema used list_price while the product page rendered
    combination_info['price'], so every discounted product advertised a price
    the customer would never be charged. Merchant Center reads that as a price
    mismatch; the SERP quoted the higher number.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env['website'].search([], limit=1)
        self.product = self.env['product.template'].create({
            'name': 'Balance Bike 14 inch',
            'list_price': 69.99,
            'is_published': True,
        })

    def _schema(self):
        return json.loads(self.product.get_schema_jsonld(self.website.name))

    def test_undiscounted_price_matches_list_price(self):
        self.assertEqual(self._schema()['offers']['price'], '69.99')

    def test_discounted_price_is_the_price_charged_not_the_list_price(self):
        pricelist = self.env['product.pricelist'].create({
            'name': 'Test 17.5% off',
            'item_ids': [(0, 0, {
                'compute_price': 'percentage',
                'percent_price': 17.5,
                'applied_on': '3_global',
            })],
        })
        product = self.product.with_context(pricelist=pricelist.id)
        charged = product._website_offer_price()
        self.assertLess(
            charged, product.list_price,
            'the pricelist should have produced a discount to test against',
        )
        data = json.loads(product.get_schema_jsonld(self.website.name))
        self.assertEqual(data['offers']['price'], '%.2f' % charged)
        self.assertNotEqual(data['offers']['price'], '69.99')

    def test_price_falls_back_to_list_price_without_combination_info(self):
        # A template with no variant cannot produce combination info; the offer
        # must still carry a price rather than raising or emitting 0.00.
        self.assertEqual(
            '%.2f' % self.product._website_offer_price(),
            self._schema()['offers']['price'],
        )


@tagged('post_install', '-at_install')
class TestBreadcrumbWebsiteBoundary(TransactionCase):
    """The breadcrumb must not walk into another website's category tree.

    Live defect this covers: 'Ride-Ons' (WhatYouNeed) has 'Toys'
    (ecomsuperstore) as its parent, so a correctly-scoped leaf still emitted
    /shop/category/toys-88 — a 404 on whatyouneed.com.au, inside a
    BreadcrumbList Google reads.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env['website'].search([], limit=1)
        self.other = self.env['website'].create({
            'name': 'Other Storefront',
            'domain': 'https://other.example',
        })
        self.foreign_root = self.env['product.public.category'].create({
            'name': 'Toys',
            'website_id': self.other.id,
        })
        self.local_leaf = self.env['product.public.category'].create({
            'name': 'Ride-Ons',
            'parent_id': self.foreign_root.id,
            'website_id': self.website.id,
        })
        self.product = self.env['product.template'].create({
            'name': 'Balance Bike',
            'list_price': 69.99,
            'is_published': True,
            'public_categ_ids': [(6, 0, [self.local_leaf.id])],
        })

    def _crumb_names(self):
        data = json.loads(self.product.get_breadcrumb_jsonld(self.website.name))
        return [i['name'] for i in data['itemListElement']]

    def test_local_leaf_is_still_emitted(self):
        self.assertIn('Ride-Ons', self._crumb_names())

    def test_ancestor_on_another_website_is_dropped(self):
        self.assertNotIn('Toys', self._crumb_names())

    def test_positions_stay_contiguous_after_truncation(self):
        data = json.loads(self.product.get_breadcrumb_jsonld(self.website.name))
        items = data['itemListElement']
        self.assertEqual(
            [i['position'] for i in items],
            list(range(1, len(items) + 1)),
        )


@tagged('post_install', '-at_install')
class TestMerchantPolicies(TransactionCase):
    """shippingDetails may only claim free shipping when it is actually free."""

    def setUp(self):
        super().setUp()
        self.website = self.env['website'].search([], limit=1)
        self.env['ir.config_parameter'].sudo().set_param(
            'rezads_seo.free_shipping_threshold', '150'
        )
        self.env['ir.config_parameter'].sudo().set_param(
            'rezads_seo.return_days', '30'
        )

    def _offer(self, price):
        product = self.env['product.template'].create({
            'name': 'Policy Fixture %s' % price,
            'list_price': price,
            'is_published': True,
        })
        return json.loads(product.get_schema_jsonld(self.website.name))['offers']

    def test_return_policy_is_always_declared(self):
        policy = self._offer(19.99)['hasMerchantReturnPolicy']
        self.assertEqual(policy['merchantReturnDays'], 30)
        self.assertEqual(policy['applicableCountry'], 'AU')

    def test_free_shipping_declared_above_the_threshold(self):
        shipping = self._offer(199.00)['shippingDetails']
        self.assertEqual(shipping['shippingRate']['value'], '0')

    def test_shipping_omitted_below_the_threshold(self):
        # The real rate depends on basket and destination, which this context
        # cannot know. Omitting beats inventing a number Google will check.
        self.assertNotIn('shippingDetails', self._offer(19.99))


@tagged('post_install', '-at_install')
class TestCategoryMeta(TransactionCase):
    """22 of 24 category pages shipped with no meta description at all."""

    def setUp(self):
        super().setUp()
        self.website = self.env['website'].search([], limit=1)
        self.category = self.env['product.public.category'].create({
            'name': 'Drinking',
            'website_id': self.website.id,
        })

    def test_empty_category_gets_no_invented_description(self):
        self.assertFalse(self.category._build_category_meta_description())

    def test_description_reports_the_real_product_count(self):
        for i in range(3):
            self.env['product.template'].create({
                'name': 'Beer Snorkel %s' % i,
                'list_price': 24.99,
                'is_published': True,
                'public_categ_ids': [(6, 0, [self.category.id])],
            })
        description = self.category._build_category_meta_description()
        self.assertIn('3 drinking products', description)
        self.assertIn('24.99', description)
        self.assertLessEqual(len(description), 158)

    def test_hand_written_description_is_never_overwritten(self):
        self.category.website_meta_description = 'Hand written and better.'
        self.category._set_category_seo_defaults()
        self.assertEqual(
            self.category.website_meta_description, 'Hand written and better.'
        )

    def test_title_carries_the_website_name(self):
        title = self.category._build_category_meta_title()
        self.assertTrue(title.startswith('Drinking'))
        self.assertLessEqual(len(title), 60)


@tagged('post_install', '-at_install')
class TestSiteSchema(TransactionCase):
    """Organization and WebSite must name this storefront, never another one.

    website.domain is blank on three records in this database and Odoo then
    falls back to the shared base URL, which is why those storefronts emit
    ecomsuperstore.com.au as their canonical. Schema must not repeat that
    mistake by quietly borrowing a URL that belongs to a different business.
    """

    def test_schema_uses_the_websites_own_domain(self):
        website = self.env['website'].create({
            'name': 'Own Domain Store',
            'domain': 'https://www.ownstore.example',
        })
        data = json.loads(website.get_site_jsonld())
        for node in data['@graph']:
            self.assertTrue(node['url'].startswith('https://www.ownstore.example'))

    def test_configured_domain_wins_over_the_shared_base_url(self):
        website = self.env['website'].create({
            'name': 'Own Domain Store 2',
            'domain': 'https://www.ownstore2.example',
        })
        self.assertEqual(
            website._seo_canonical_domain(), 'https://www.ownstore2.example'
        )

    def test_blank_domain_never_returns_a_sibling_domain(self):
        # The live defect: with a blank domain Odoo hands back the shared
        # web.base.url, so three storefronts canonicalise into ecomsuperstore.
        # Outside a request there is no host to fall back to, so the only
        # guarantee available here is that it is not another website's domain.
        sibling = self.env['website'].create({
            'name': 'Sibling Store',
            'domain': 'https://www.sibling.example',
        })
        blank = self.env['website'].create({
            'name': 'No Domain Store',
            'domain': False,
        })
        self.assertNotIn('sibling.example', blank._seo_canonical_domain())
        self.assertNotEqual(
            blank._seo_canonical_domain(), sibling._seo_canonical_domain()
        )

    def test_graph_carries_both_organization_and_website(self):
        website = self.env['website'].search([], limit=1)
        types = [n['@type'] for n in json.loads(website.get_site_jsonld())['@graph']]
        self.assertIn('Organization', types)
        self.assertIn('WebSite', types)


class TestPaginatedTitles(TransactionCase):
    """Every paginated category page carried page one's title.

    /shop/category/sunglasses-wrap-sunglasses-128/page/2 and /page/3 both
    rendered "Wrap Polarised Sunglasses | Mangrove Jacks" and both canonicalised
    to themselves, so Google saw identical pages claiming the same thing. It
    ranked page 2 at position 1.5 on 186 impressions for one click, while page
    one — the page that should rank — was not shown.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env['website'].search([], limit=1)

    def _at(self, path):
        """Run the helpers as though this request were for `path`."""
        from unittest.mock import patch
        import odoo.addons.RezaDs_seo_auto.models.website as mod

        class _Req:
            class httprequest:
                pass
        req = _Req()
        req.httprequest.path = path
        return patch.object(mod, 'request', req)

    def test_page_number_read_from_the_path(self):
        with self._at('/shop/category/sunglasses-4/page/3'):
            self.assertEqual(self.website._seo_page_number(), 3)

    def test_unpaginated_path_is_page_zero(self):
        with self._at('/shop/category/sunglasses-4'):
            self.assertEqual(self.website._seo_page_number(), 0)

    def test_trailing_slash_still_parses(self):
        with self._at('/shop/category/sunglasses-4/page/2/'):
            self.assertEqual(self.website._seo_page_number(), 2)

    def test_a_path_segment_named_page_is_not_a_page_number(self):
        """/page/about must not be read as pagination."""
        with self._at('/page/about'):
            self.assertEqual(self.website._seo_page_number(), 0)

    def test_page_one_gets_no_suffix(self):
        """Page one keeps the clean title; only 2+ are ambiguous."""
        category = self.env['product.public.category'].create(
            {'name': 'Wrap', 'website_meta_title': 'Wrap Polarised Sunglasses'})
        with self._at('/shop/category/wrap-1'):
            self.assertFalse(self.website._seo_paginated_title(category))

    def test_paginated_title_numbers_the_meta_title(self):
        category = self.env['product.public.category'].create(
            {'name': 'Wrap', 'website_meta_title': 'Wrap Polarised Sunglasses'})
        with self._at('/shop/category/wrap-1/page/2'):
            self.assertEqual(self.website._seo_paginated_title(category),
                             'Wrap Polarised Sunglasses | Page 2')

    def test_falls_back_to_the_record_name(self):
        """A category with no meta title must still get a distinct title."""
        category = self.env['product.public.category'].create({'name': 'Shield'})
        with self._at('/shop/category/shield-1/page/4'):
            title = self.website._seo_paginated_title(category)
            self.assertIn('Shield', title)
            self.assertTrue(title.endswith('| Page 4'))

    def test_no_object_still_yields_a_title(self):
        with self._at('/shop/page/2'):
            title = self.website._seo_paginated_title(False)
            self.assertTrue(title.endswith('| Page 2'))

    # ---- per-website title suffix -------------------------------------------------
    #
    # website_meta_title is stored once and Odoo scopes it by language, never by website.
    # 785 live products in this database are carried by two or more storefronts, so a title
    # with one site's name baked in is wrong everywhere else the same product appears.

    def test_no_suffix_configured_changes_nothing(self):
        """A site with no suffix must behave exactly as before."""
        self.website.seo_title_suffix = False
        category = self.env['product.public.category'].create(
            {'name': 'Wrap', 'website_meta_title': 'Wrap Polarised Sunglasses'})
        with self._at('/shop/category/wrap-1'):
            self.assertFalse(self.website._seo_site_title(category))

    def test_suffix_is_appended_to_the_meta_title(self):
        self.website.seo_title_suffix = ' | Sunglass Superstore'
        category = self.env['product.public.category'].create(
            {'name': 'Wrap', 'website_meta_title': 'Wrap Polarised Sunglasses'})
        with self._at('/shop/category/wrap-1'):
            self.assertEqual(self.website._seo_site_title(category),
                             'Wrap Polarised Sunglasses | Sunglass Superstore')

    def test_suffix_composes_with_pagination(self):
        self.website.seo_title_suffix = ' | SGS'
        category = self.env['product.public.category'].create(
            {'name': 'Wrap', 'website_meta_title': 'Wrap Polarised'})
        with self._at('/shop/category/wrap-1/page/2'):
            self.assertEqual(self.website._seo_site_title(category),
                             'Wrap Polarised | Page 2 | SGS')

    def test_a_title_already_ending_in_the_suffix_is_left_alone(self):
        """Otherwise a regenerated title doubles the site name on every render."""
        self.website.seo_title_suffix = ' | Sunglass Superstore'
        category = self.env['product.public.category'].create(
            {'name': 'Wrap',
             'website_meta_title': 'Wrap Polarised Sunglasses | Sunglass Superstore'})
        with self._at('/shop/category/wrap-1'):
            self.assertFalse(self.website._seo_site_title(category))

    def test_the_core_is_trimmed_not_the_suffix(self):
        """A title cut mid-way through the site name reads like a bug."""
        self.website.seo_title_suffix = ' | Sunglass Superstore'
        category = self.env['product.public.category'].create(
            {'name': 'Wrap',
             'website_meta_title': 'Wrap Polarised Sunglasses In Every Colourway We Stock'})
        with self._at('/shop/category/wrap-1'):
            title = self.website._seo_site_title(category)
            self.assertTrue(title.endswith(' | Sunglass Superstore'))
            self.assertLessEqual(len(title), 60)
            self.assertTrue(title.startswith('Wrap Polarised'))

    # ---- per-website overrides ----------------------------------------------------

    def _override(self, product, **vals):
        return self.env['product.website.seo'].create(
            dict(product_tmpl_id=product.id, website_id=self.website.id, **vals))

    def test_no_override_uses_the_shared_field(self):
        """Most of the catalogue has no override and must be unaffected."""
        product = self.env['product.template'].create(
            {'name': 'Adder C1', 'website_meta_title': 'Adder C1 Polarised Sunglasses'})
        self.assertEqual(
            product._seo_for_website(self.website, 'website_meta_title'),
            'Adder C1 Polarised Sunglasses')

    def test_an_override_wins_on_its_own_website(self):
        product = self.env['product.template'].create(
            {'name': 'Adder C1', 'website_meta_title': 'Adder C1 Polarised Sunglasses'})
        self._override(product, meta_title='Adder C1 Fishing Sunglasses')
        self.assertEqual(
            product._seo_for_website(self.website, 'website_meta_title'),
            'Adder C1 Fishing Sunglasses')

    def test_an_empty_override_field_falls_back(self):
        """A row created for one field must not blank the others."""
        product = self.env['product.template'].create(
            {'name': 'Adder C1',
             'website_meta_title': 'Adder C1 Polarised Sunglasses',
             'website_meta_description': 'Shared description.'})
        self._override(product, meta_title='Adder C1 Fishing Sunglasses')
        self.assertEqual(
            product._seo_for_website(self.website, 'website_meta_description'),
            'Shared description.')

    def test_one_row_per_product_per_website(self):
        from psycopg2 import IntegrityError
        from odoo.tools import mute_logger
        product = self.env['product.template'].create({'name': 'Adder C1'})
        self._override(product, meta_title='First')
        with self.assertRaises(IntegrityError), mute_logger('odoo.sql_db'):
            with self.cr.savepoint():
                self._override(product, meta_title='Second')

    # ---- per-website settings -------------------------------------------------------

    def test_website_value_beats_the_global_parameter(self):
        """$69 on one storefront and $150 on another cannot share a config parameter."""
        self.env['ir.config_parameter'].sudo().set_param(
            'rezads_seo.free_shipping_threshold', '150')
        self.website.seo_free_shipping_threshold = 69
        self.assertEqual(
            float(self.website._get_seo_param('free_shipping_threshold', '0')), 69)

    def test_an_unset_website_value_falls_through_to_the_global(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'rezads_seo.free_shipping_threshold', '150')
        self.website.seo_free_shipping_threshold = 0
        self.assertEqual(
            float(self.website._get_seo_param('free_shipping_threshold', '0')), 150)

    def test_a_suffix_leaving_no_room_is_refused(self):
        """Publishing the site name alone is worse than publishing the product name alone."""
        self.website.seo_title_suffix = ' | The Longest Storefront Name Anybody Has Ever Used Here'
        category = self.env['product.public.category'].create(
            {'name': 'Wrap', 'website_meta_title': 'Wrap Polarised Sunglasses'})
        with self._at('/shop/category/wrap-1'):
            self.assertFalse(self.website._seo_site_title(category))
