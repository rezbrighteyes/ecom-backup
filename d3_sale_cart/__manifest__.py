# -*- coding: utf-8 -*-
{
    'name': "D3 Sale Cart",

    'summary': """
Automatically generates discount coupons for abandoned carts using loyalty programs and sends them as part of follow‑up recovery emails.
    """,

    'description': """
This module extends Odoo’s eCommerce and Loyalty programs by enabling automated coupon creation for abandoned carts. When a customer abandons their shopping cart, the system can generate a loyalty coupon and include it in recovery emails to encourage conversion. The administrator can configure the number of validity days, the loyalty program used, and enable or disable coupon generation per website.
    """,

    'author': "d-3system",
    'contribuitors': ["Juan Arcos juanparmer@gmail.com"],
    'website': "https://d-3system.com.au/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Website/Website',
    'version': '18.0.2.1.1',

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
