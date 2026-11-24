from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

# A short copy of the Google taxonomy file, same format: a comment first line,
# "<id> - <path>" lines, and a trailing newline (so the last split item is empty).
FAKE_TAXONOMY = (
    "# Google_Product_Taxonomy_Version: 2021-09-21\n"
    "166 - Apparel & Accessories\n"
    "167 - Apparel & Accessories > Clothing Accessories\n"
    "178 - Apparel & Accessories > Clothing Accessories > Sunglasses\n"
    "1604 - Apparel & Accessories > Clothing\n"
)
TAXONOMY_URL = 'https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt'


class _FakeResponse:
    text = FAKE_TAXONOMY

    def raise_for_status(self):
        return None


@tagged('post_install', '-at_install')
class TestProductGoogleCategory(TransactionCase):

    def setUp(self):
        super(TestProductGoogleCategory, self).setUp()
        self.google_category = self.env['product.google.category']
        # Odoo 20 port: the base db has no demo data, so base.user_demo does not
        # exist. Use an equivalent plain internal user.
        self.user = new_test_user(self.env, login='gcat_import_user', groups='base.group_user')
        # Never call Google from a test: serve a fixed copy of the taxonomy file.
        patcher = patch(
            'odoo.addons.base_import_helper.wizard.base_import_helper.requests.get',
            return_value=_FakeResponse(),
        )
        self.mock_get = patcher.start()
        self.addCleanup(patcher.stop)

    def test_import_from_url(self):
        wizard = self.env['base_import.helper'].with_user(self.user).create({
            'mode': 'google_categ',
            'url': TAXONOMY_URL,
        })

        result = wizard.open_url(wizard.url)
        self.assertEqual(result['error'], None)

        wizard.with_user(self.user).action_import()

        self.assertEqual(
            self.google_category.search_count([]),
            len(result['content'].split('\n')) - 2,  # Exclude the 1st and the last lines
        )
        self.assertEqual(self.mock_get.call_args.args[0], TAXONOMY_URL)
        sunglasses = self.google_category.search([('code', '=', '178')])
        self.assertEqual(sunglasses.name, 'Sunglasses')
        self.assertEqual(sunglasses.parent_id.name, 'Clothing Accessories')
