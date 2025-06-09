# Copyright © 2020 Garazd Creation (https://garazd.biz)
# @author: Yurii Razumovskyi (support@garazd.biz)
# @author: Iryna Razumovska (support@garazd.biz)
# License OPL-1 (https://www.odoo.com/documentation/15.0/legal/licenses.html).

import logging

from datetime import timedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tools.float_utils import float_compare

from .common import TestProductDataFeedCommon

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install', 'product_data_feed')
class TestProductDataFeedCSV(TestProductDataFeedCommon):

    def test_01_get_csv_feed(self):
        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(self.product_desk.id):
                self.assertEqual(row['id'], str(self.product_desk.id), "Field value should be correct.")
                self.assertEqual(
                    row['price'].split(' ')[1],  # Separate currency from price
                    '199.90',
                    "Product price should be with format '%.2f'.",
                )
                self.assertTrue(row['type'], "Boolean field value should be True.")
                self.assertEqual(len(row['option']), 10, "Value should be limited to 10 symbols.")
                self.assertEqual(row['condition'], 'new', 'Column with the type "value" should have a related value.')

                # Special columns
                self.assertEqual(
                    row['special_price'].split(' ')[1], '199.9', "Product price should be without format.",
                )

                # Links
                self.assertEqual(
                    row['link'], f"{self.feed_template._get_base_url()}{self.product_desk.website_url}",
                    "The product link should be correct.",
                )

                # Availability
                self.assertEqual(
                    row['availability'],
                    'in_stock',
                    "Product should be in stock.",
                )
                self.assertEqual(
                    float_compare(float(row['qty']), 15.0, precision_digits=2), 0,
                    "15 pcs of the product should be in stock.",
                )

    def test_get_csv_feed_pricelist(self):
        self.feed_template.pricelist_id = self.pricelist.id
        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(self.product_desk.id):
                self.assertEqual(row['price'].split(' ')[1], '155.55', "Product price should be with format '%.2f'.")
                self.assertEqual(
                    row['special_price'].split(' ')[1], '155.55', "Product price should be without format.",
                )

    def test_get_csv_feed_availability_stock_out(self):
        self.feed_template.out_of_stock_mode = 'out_of_stock'
        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(self.product_paper.id):
                self.assertEqual(row['availability'], 'out_of_stock', "Product should not be in stock.")
                self.assertEqual(
                    float_compare(float(row['qty']), 0, precision_digits=2), 0,
                    "Product qty in stock should be equal 0.",
                )

    def test_get_csv_feed_availability_to_order(self):
        self.feed_template.out_of_stock_mode = 'order'
        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(self.product_paper.id):
                self.assertEqual(row['availability'], 'to_order', "Product should be available to order.")
                self.assertEqual(
                    float_compare(float(row['qty']), 0, precision_digits=2), 0,
                    "Product qty in stock should be equal 0.",
                )
                self.assertEqual(
                    row['availability_date'],
                    fields.Date.to_string(fields.Date.today() + timedelta(days=10)),
                    "Product availability date should be + 10 days from today.",
                )

    def test_get_csv_feed_stock_qty_type_virtual_available(self):
        self.feed_template.write({
            'availability_type': 'virtual_available',
            'stock_location_ids': [(4, self.location.id)],
        })
        self.env['stock.quant'].create({
            'product_id': self.product_desk.product_variant_id.id,
            'location_id': self.location.id,
            'reserved_quantity': 3.0,
        })

        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(self.product_desk.id):
                self.assertEqual(
                    float_compare(
                        float(row['qty']),
                        self.product_desk.with_context(location=self.location.id).product_variant_id.virtual_available,
                        precision_digits=2,
                    ), 0,
                    "12 pcs of the product should be available in stock "
                    "(15 - 3 reserved).")

    def test_get_csv_feed_stock_qty_type_free_qty(self):
        self.feed_template.write({'availability_type': 'free_qty'})
        self.env['stock.quant'].create({
            'product_id': self.product_desk.product_variant_id.id,
            'location_id': self.location.id,
            'reserved_quantity': 10.0,
        })

        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(self.product_desk.id):
                self.assertEqual(
                    float_compare(float(row['qty']), 5.0, precision_digits=2), 0,
                    "5 pcs of the product should be free in stock (15 - 10 reserved).",
                )

    def test_get_csv_feed_currency(self):
        self.feed_template.currency_id = self.env.ref('base.UAH').id
        for row in self._get_csv_lines(self.feed_template):
            self.assertEqual(
                row['currency'], self.env.ref('base.UAH').name,
                "Price currency should be taken from the pricelist.",
            )

        self.feed_template.pricelist_id = self.pricelist.id

        for row in self._get_csv_lines(self.feed_template):
            self.assertEqual(
                row['currency'], self.env.ref('base.EUR').name,
                "Price currency should be taken from the feed currency field.",
            )

    def test_special_types_price_and_taxes(self):
        tax_1 = self.env['account.tax'].create({
            'name': '15% tax',
            'amount_type': 'percent',
            'amount': 15,
            'price_include': False,
            'sequence': 1,
        })
        tax_2_incl = self.env['account.tax'].create({
            'name': '15% tax incl',
            'amount_type': 'percent',
            'amount': 15,
            'price_include': True,
            'include_base_amount': True,
            'sequence': 2,
        })
        product = self.env['product.template'].create({
            'name': 'Product Data Feed - Test',
            'is_storable': True,
            'list_price': 1000.0,
            'is_published': True,
        })

        self.feed_template.column_ids = [
            (0, 0, {
                'name': 'price_with_tax',
                'type': 'special',
                'special_type': 'price_with_tax',
                'format': '%.4f',
            }),
            (0, 0, {
                'name': 'price_wo_tax',
                'type': 'special',
                'special_type': 'price_wo_tax',
                'format': '%.4f',
            }),
        ]

        # def check_product_price_and_taxes():

        # Tax amount is not included to the price
        product.taxes_id = [(5, 0), (4, tax_1.id)]

        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(product.id):
                self.assertEqual(
                    float_compare(
                        float(row['price_wo_tax']), 1000.0, precision_digits=4
                    ),
                    0,
                    "Product price without taxes must be 1000.0, "
                    "we got %s." % row['price_wo_tax'],
                )
                self.assertEqual(
                    float_compare(
                        float(row['price_with_tax']), 1150.0, precision_digits=4
                    ),
                    0,
                    "Product price with taxes must be 1150.0.",
                )

        # Tax amount is included to the price
        product.taxes_id = [(5, 0), (4, tax_2_incl.id)]

        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(product.id):
                self.assertEqual(
                    float_compare(
                        float(row['price_wo_tax']), 869.57, precision_digits=4
                    ),
                    0,
                    "Product price without the tax included in price must be 869.57",
                )
                self.assertEqual(
                    float_compare(
                        float(row['price_with_tax']), 1000.0, precision_digits=4
                    ),
                    0,
                    "Product price with the tax included in price must be 1000.0",
                )

    def test_get_csv_feed_product_attribute(self):
        # Test case for product template feed
        for row in self._get_csv_lines(self.feed_template):
            if row['id'] == str(self.product_desk.id):
                self.assertEqual(
                    row['attribute'], "Wood", "Product attribute value is not as expected.",
                )

        # Test case for product feed
        for row in self._get_csv_lines(self.feed_product):
            if row['id'] == str(self.product_desk.product_variant_id.id):
                self.assertEqual(
                    row['attribute_brand'], "Desks for all", "Product attribute value is not as expected.",
                )

        # user = self.env.user
        #
        # # Switch to show prices with taxes
        # self.env.ref('account.group_show_line_subtotals_tax_excluded').users -= user
        # self.env.ref('account.group_show_line_subtotals_tax_included').users |= user
        # self.assertTrue(
        #     user.has_group('account.group_show_line_subtotals_tax_included')
        # )
        # check_product_price_and_taxes()
        #
        # # Switch to show prices without taxes
        # self.env.ref('account.group_show_line_subtotals_tax_included').users -= user
        # self.env.ref('account.group_show_line_subtotals_tax_excluded').users |= user
        # self.assertTrue(
        #     user.has_group('account.group_show_line_subtotals_tax_excluded')
        # )
        # check_product_price_and_taxes()
