# -*- coding: utf-8 -*-
{
    'name': "D3 Stcok E-com",

    'summary': "Stcok E-com",

    'description': """
Modify Delivery Slip report
    """,

    'author': 'Dimension3',
    'contributors': ['Juan Arcos juanparmer@gmail.com'],
    'website': 'https://d-3.com.au',

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Inventory/Inventory',
    'version': '18.0.1.0.2',

    # any module necessary for this one to work correctly
    'depends': ['stock'],

    # always loaded
    'data': [
        'templates/stock_picking_template.xml'
    ],

    # License
    'license': 'OPL-1'
}

