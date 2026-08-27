import json

from odoo.tests import TransactionCase, tagged

from odoo.addons.RezaDs_seo_auto.models.product_template import _plain_slug


@tagged('post_install', '-at_install')
class TestSchemaUrls(TransactionCase):
    """Every URL the module puts into JSON-LD must resolve.

    The bug these cover: the module built '/shop/<seo_name>' and
    '/shop/category/<internal categ name>'. Odoo routes on '<slug>-<id>' and
    serves public categories, not internal ones, so all three URLs on a product
    page returned 404 while the canonical tag was correct.
    """

    def setUp(self):
        super().setUp()
        self.website = self.env['website'].search([], limit=1)
        self.root = self.env['product.public.category'].create({
            'name': 'Sunglasses',
            'website_id': self.website.id,
        })
        self.child = self.env['product.public.category'].create({
            'name': 'Wrap Sunglasses',
            'parent_id': self.root.id,
            'website_id': self.website.id,
        })
        self.product = self.env['product.template'].create({
            'name': 'Mangrove Jacks Adder C1 Black / Smoke Polarised Lenses',
            'list_price': 59.99,
            'barcode': '9340457009623',
            'is_published': True,
            'public_categ_ids': [(6, 0, [self.root.id, self.child.id])],
        })

    # -- helpers -----------------------------------------------------------

    def _schema(self):
        return json.loads(self.product.get_schema_jsonld(self.website.name))

    def _breadcrumb(self):
        return json.loads(self.product.get_breadcrumb_jsonld(self.website.name))

    # -- the product URL ---------------------------------------------------

    def test_canonical_path_carries_the_record_id(self):
        path = self.product._canonical_path()
        self.assertTrue(
            path.endswith('-%s' % self.product.id),
            "product path must end in the id the router matches on, got %r" % path,
        )

    def test_canonical_path_matches_website_url(self):
        self.assertEqual(self.product._canonical_path(), self.product.website_url)

    def test_schema_url_and_offer_url_agree_with_the_canonical(self):
        data = self._schema()
        self.assertTrue(data['url'].endswith(self.product.website_url))
        self.assertEqual(data['url'], data['offers']['url'])

    def test_breadcrumb_leaf_is_the_product_url(self):
        items = self._breadcrumb()['itemListElement']
        self.assertTrue(items[-1]['item'].endswith(self.product.website_url))

    # -- the category URL --------------------------------------------------

    def test_breadcrumb_uses_public_categories_not_the_internal_one(self):
        names = [i['name'] for i in self._breadcrumb()['itemListElement']]
        self.assertIn('Wrap Sunglasses', names)

    def test_breadcrumb_walks_the_whole_ancestor_chain(self):
        names = [i['name'] for i in self._breadcrumb()['itemListElement']]
        self.assertEqual(names[1], 'Shop')
        self.assertLess(names.index('Sunglasses'), names.index('Wrap Sunglasses'))
        self.assertEqual(names[-1], self.product.name)

    def test_breadcrumb_category_url_carries_the_record_id(self):
        for item in self._breadcrumb()['itemListElement']:
            if '/shop/category/' in item['item']:
                self.assertRegex(item['item'], r'-\d+$')

    def test_breadcrumb_skips_categories_belonging_to_another_website(self):
        other = self.env['website'].create({'name': 'Other', 'domain': 'other.example'})
        foreign = self.env['product.public.category'].create({
            'name': 'Foreign Only',
            'website_id': other.id,
        })
        self.product.public_categ_ids = [(4, foreign.id)]
        names = [i['name'] for i in self._breadcrumb()['itemListElement']]
        self.assertNotIn('Foreign Only', names)

    def test_positions_are_contiguous_from_one(self):
        items = self._breadcrumb()['itemListElement']
        self.assertEqual(
            [i['position'] for i in items],
            list(range(1, len(items) + 1)),
        )

    # -- gtin --------------------------------------------------------------

    def test_gtin13_emitted_for_a_13_digit_barcode(self):
        data = self._schema()
        self.assertEqual(data['gtin13'], '9340457009623')
        self.assertEqual(data['offers']['gtin13'], '9340457009623')

    def test_gtin13_omitted_when_the_barcode_is_not_a_gtin13(self):
        self.product.barcode = 'ADDER-C1'
        data = self._schema()
        self.assertNotIn('gtin13', data)
        self.assertNotIn('gtin13', data['offers'])

    def test_gtin13_omitted_when_there_is_no_barcode(self):
        self.product.barcode = False
        self.assertNotIn('gtin13', self._schema())

    # -- redirects ---------------------------------------------------------

    def test_renaming_creates_a_redirect_between_two_real_urls(self):
        old_slug = self.product.seo_name
        self.product.name = 'Mangrove Jacks Adder C1 Renamed'
        rewrite = self.env['website.rewrite'].search(
            [('url_from', '=', '/shop/%s-%s' % (old_slug, self.product.id))], limit=1
        )
        self.assertTrue(rewrite, 'redirect should be keyed on the URL that was live')
        self.assertEqual(rewrite.url_to, self.product._canonical_path())

    # -- slug helper -------------------------------------------------------

    def test_plain_slug_keeps_stop_words(self):
        # _make_slug drops them for a hand-built seo_name; a router slug must not.
        self.assertEqual(_plain_slug('Hook and Ring Toss'), 'hook-and-ring-toss')

    def test_plain_slug_strips_punctuation_and_accents(self):
        self.assertEqual(_plain_slug('Jack’s  Café / Wrap'), 'jacks-cafe-wrap')
