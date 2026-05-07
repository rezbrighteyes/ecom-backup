# -*- coding: utf-8 -*-
{
    'name': "D3 Credit Control",

    'summary': "Account Credit Control",

    'description': """
        Account Credit Control
        - Blocking customer (partner) due to credit limit.
        - Blocking customer (partner) due to overdue invoices.
    """,

    'author': "D-3system",
    'contributors': ["Juan Arcos juanparmer@gmail.com"],
    'website': "https://www.d-3system.com.au",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Uncategorized',
    'contribuitors': ['Juan Arcos juanparmer@gmail.com'],
    'version': '18.0.0.0.2',

    # any module necessary for this one to work correctly
    'depends': ['sale'],

    # always loaded
    'data': [
        'views/res_config_view.xml',
        'views/res_partner_view.xml',
    ],

    # License
    'license': 'OPL-1',
}
