# -*- coding: utf-8 -*-
{
    'name': "D3 External API",

    'summary': """
Integrates Odoo with an external Odoo database using XML‑RPC. Automatically synchronizes products, product variants, images, stock quants, purchase orders, sales orders, and stock movements between systems. Includes connection validation, scheduled jobs, and per‑company configuration.
    """,

    'description': """
This module extends Odoo 18 with a complete framework for synchronizing data between two Odoo instances through XML‑RPC. It supports product import (including templates, variants, attributes, and images), stock quant synchronization, and the automatic creation and updating of sales orders in the external system when purchase orders are processed locally.
The module also provides a configuration panel per company, a connection checker, and utilities to reconcile remote IDs with local records. It is designed for distributed environments where inventory, sales, and product data must be kept aligned across different Odoo databases.
    """,

    'author': 'd-3system',
    'contributors': ['Juan Arcos juanparmer@gmail.com'],
    'website': 'https://sys.d-3system.com.au',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Inventory/Inventory',
    'version': '20.0.3.1.1',

    # any module necessary for this one to work correctly
    'depends': [
        'purchase_stock',
    ],

    # always loaded
    'data': [
        'data/stock_warehouse_data.xml',
        'data/ir_cron_data.xml',
        'data/product_tag_data.xml',
        'views/product_product_views.xml',
        'views/purchase_order_view.xml',
        'views/res_config_view.xml',
        # 'wizard/external_api_view.xml',
        'security/ir.access.csv',
    ],

    # Hook
    # 'post_init_hook': '_post_init_hook',

    # License
    'license': 'OPL-1'
}
