# -*- coding: utf-8 -*-
{
    'name': "D3 Sale Sign",

    'summary': "Sale Sign",

    'description': """
        Enables the signing of a sales order on the backend.
    """,

    'author': "d-3system",
    'contribuitors': ["Juan Arcos juanparmer@gmail.com"],
    'website': "https://d-3system.com.au/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Sales/Sales',
    'version': '18.1',

    # any module necessary for this one to work correctly
    'depends': ['sale'],

    # always loaded
    'data': [
        'views/sale_order_view.xml',
    ],

    # license
    'license': 'OPL-1',
}
