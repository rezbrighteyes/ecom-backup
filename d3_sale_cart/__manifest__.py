# -*- coding: utf-8 -*-
{
    'name': "D3 Sale Cart",

    'summary': "Sale Cart Recovery",

    'description': """
        Send a discount coupon as part of a follow-up email for abandoned carts.
    """,

    'author': "d-3system",
    'contribuitors': ["Juan Arcos juanparmer@gmail.com"],
    'website': "https://d-3system.com.au/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Website/Website',
    'version': '18.0.0.0.1',

    # any module necessary for this one to work correctly
    'depends': [
        'loyalty',
        'website_sale'
    ],

    # always loaded
    'data': [
        # 'data/loyalty_program_data.xml',
        'views/res_config_view.xml',
    ],

    # license
    'license': 'OPL-1',
}
