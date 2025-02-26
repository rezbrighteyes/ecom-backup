# -*- coding: utf-8 -*-
{
    'name': "D3 Sale Block",

    'summary': "Sale Block",

    'description': """
        9.2 Block sale if over the credit limit
    """,

    'author': 'Dimension3',
    'contributors': ['Juan Arcos juanparmer@gmail.com'],
    'website': 'https://d-3.com.au',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Sales/Sales',
    'version': '17.1',

    # any module necessary for this one to work correctly
    'depends': ['sale'],

    # always loaded
    'data': [
        'view/sale_order_view.xml',
        'view/payment_portal_template.xml',
        'view/payment_provider_views.xml',
    ],

    'assets': {
        'web.assets_frontend': [
            'd3_sale_block/static/src/**/*',
        ]
    },

    # License
    'license': 'LGPL-3'
}
