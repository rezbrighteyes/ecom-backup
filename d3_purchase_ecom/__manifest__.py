# -*- coding: utf-8 -*-
{
    'name': "D3 Purchase E-com",

    'summary': "Purchase E-com",

    'description': """
Modify Purchase report, add Total Lines, Total QTY
    """,

    'author': 'Dimension3',
    'contributors': ['Juan Arcos juanparmer@gmail.com'],
    'website': 'https://d-3.com.au',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Inventory/Purchase',
    'version': '18.1',

    # any module necessary for this one to work correctly
    'depends': ['purchase'],

    # always loaded
    'data': [
        'templates/purchase_order_template.xml'
    ],

    # License
    'license': 'LGPL-3'
}

