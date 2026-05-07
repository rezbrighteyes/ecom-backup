# -*- coding: utf-8 -*-
{
    'name': "D3 Picking Note",

    'summary': "Picking Note",

    'description': """
        Add Picking Note on Sales
    """,

    'author': "d-3systems",
    'contribuitors': ["Juan Arcos juanparmer@gmail.com"],
    'website': "https://d-3system.com.au/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Sale/Sales',
    'version': '18.0.1.1.1',

    # any module necessary for this one to work correctly
    'depends': ['sale_stock'],

    # always loaded
    'data': [
        'views/sale_order_view.xml',
    ],

    # license
    'license': 'OPL-1',
}

