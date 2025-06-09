# Copyright © 2020 Garazd Creation (https://garazd.biz)
# @author: Yurii Razumovskyi (support@garazd.biz)
# @author: Iryna Razumovska (support@garazd.biz)
# License OPL-1 (https://www.odoo.com/documentation/15.0/legal/licenses.html).

import csv

from odoo.tests.common import HttpCase


class TestProductDataFeedCommon(HttpCase):

    def setUp(self):
        super(TestProductDataFeedCommon, self).setUp()
        self.location = self.env.ref('stock.stock_location_stock')
        attribute_material = self.env['product.attribute'].create({'name': 'Material'})
        attribute_brand = self.env['product.attribute'].create({
            'name': 'Brand',
            'create_variant': 'no_variant',
        })
        value_material_1 = self.env['product.attribute.value'].create({
            'name': 'Wood',
            'attribute_id': attribute_material.id,
        })
        value_material_2 = self.env['product.attribute.value'].create({
            'name': 'Steal',
            'attribute_id': attribute_material.id,
        })
        value_brand = self.env['product.attribute.value'].create({
            'name': 'Desks for all',
            'attribute_id': attribute_brand.id,
        })
        self.product_desk = self.env['product.template'].create({
            'name': 'Product Data Feed - Desk',
            'is_storable': True,
            'list_price': 199.90,
            'default_code': 'DESK',
            'description_sale': '160x80cm, with large legs.',
            'sale_delay': 5,
            'attribute_line_ids': [
                # flake8: noqa: E501
                (0, 0, {'attribute_id': attribute_material.id, 'value_ids': [(6, 0, [value_material_1.id, value_material_2.id])]}),
                (0, 0, {'attribute_id': attribute_brand.id, 'value_ids': [(6, 0, [value_brand.id])]}),
            ],
            'is_published': True,
        })
        self.product_paper = self.env['product.template'].create({
            'name': 'Product Data Feed - Paper A4',
            'is_storable': True,
            'list_price': 47.99,
            'default_code': 'A4/500',
            'sale_delay': 10,
            'is_published': True,
        })
        stock_quant = self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.product_desk.product_variant_id.id,
            'location_id': self.location.id,
            'inventory_quantity': 15,
        })
        stock_quant.action_apply_inventory()  # Odoo 15.0

        self.pricelist = self.env['product.pricelist'].create({
            'name': 'Test Pricelist',
            'currency_id': self.env.ref('base.EUR').id,
            'item_ids': [
                (0, 0, {'applied_on': '1_product',
                        'compute_price': 'fixed',
                        'product_tmpl_id': self.product_desk.id,
                        'fixed_price': 155.55})]
        })
        self.recipient = self.env['product.data.feed.recipient'].create({
            'name': 'Test Recipient',
            'special_avail_in': 'in_stock',
            'special_avail_out': 'out_of_stock',
            'special_avail_order': 'to_order',
        })
        self.value_condition_new = self.env[
            'product.data.feed.column.value'].create({
                'recipient_id': self.recipient.id,
                'column_name': 'condition',
                'name': 'new',
            })
        self.value_condition_used = self.env[
            'product.data.feed.column.value'].create({
                'recipient_id': self.recipient.id,
                'column_name': 'condition',
                'name': 'used',
            })

        # Product Feeds
        # Product Template
        self.feed_template = self.env['product.data.feed'].with_context(**{
            'mail_create_nolog': True,
            'mail_notrack': True,
        }).create({
            'recipient_id': self.recipient.id,
            'name': 'Test Product Template CSV Feed',
            'model_id': self.env.ref('product.model_product_template').id,
            'file_type': 'csv',
            'use_token': True,
            'model_domain': "[('name', 'like', 'Product Data Feed -%')]",
            'availability_type': 'qty_available',
            'out_of_stock_mode': 'out_of_stock',
            'currency_position': 'before',
            'column_ids': [
                (0, 0, {'type': 'field',
                        'name': 'id',
                        'field_id': self.env.ref('product.field_product_template__id').id,
                        'limit': 5,
                        'format': '%d',
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'name': 'price',
                        'special_type': 'price',
                        'format': '%.2f',
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'name': 'currency',
                        'special_type': 'price_currency'}),
                # Model Field - Selection
                (0, 0, {'type': 'field',
                        'name': 'type',
                        'field_id': self.env.ref('product.field_product_product__type').id,
                        'is_required': True}),
                (0, 0, {'type': 'text',
                        'name': 'option',
                        'value': 'SampleSample',
                        'limit': 10,
                        'is_required': False}),
                (0, 0, {'type': 'value',
                        'name': 'condition',
                        'value_id': self.value_condition_new.id,
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'special_type': 'price',
                        'name': 'special_price',
                        'is_required': False}),
                (0, 0, {'type': 'special',
                        'special_type': 'link',
                        'name': 'link',
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'special_type': 'image_link',
                        'name': 'image_link',
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'special_type': 'availability',
                        'name': 'availability',
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'special_type': 'stock',
                        'name': 'qty',
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'special_type': 'availability_date',
                        'name': 'availability_date',
                        'is_required': False}),
                (0, 0, {'type': 'special',
                        'name': 'attribute',
                        'special_type': 'product_attribute',
                        'product_attribute_id': attribute_material.id}),
            ],
        })
        self.feed_template.action_generate_token()

        # Product Feeds
        # Product
        self.feed_product = self.env['product.data.feed'].with_context(**{
            'mail_create_nolog': True,
            'mail_notrack': True,
        }).create({
            'recipient_id': self.recipient.id,
            'name': 'Test Product CSV Feed',
            'model_id': self.env.ref('product.model_product_product').id,
            'file_type': 'csv',
            'use_token': True,
            'model_domain': "[('name', 'like', 'Product Data Feed -%')]",
            'availability_type': 'qty_available',
            'out_of_stock_mode': 'out_of_stock',
            'currency_position': 'before',
            'column_ids': [
                (0, 0, {'type': 'field',
                        'name': 'id',
                        'field_id': self.env.ref(
                            'product.field_product_product__id').id,
                        'limit': 5,
                        'format': '%d',
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'name': 'price',
                        'special_type': 'price',
                        'format': '%.2f',
                        'is_required': True}),
                (0, 0, {'type': 'special',
                        'name': 'currency',
                        'special_type': 'price_currency'}),
                (0, 0, {'type': 'special',
                        'name': 'attribute_brand',
                        'special_type': 'product_attribute',
                        'product_attribute_id': attribute_brand.id}),
            ],
        })
        self.feed_product.action_generate_token()

    def _get_csv_lines(self, feed):
        content = feed.sudo().generate_data_file()
        return [line for line in csv.DictReader(content.splitlines())]
