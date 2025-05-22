# -*- coding: utf-8 -*-
{
    'name': "D3 Standard Improvements",

    'summary': "Standard Improvements",

    'description': """
This module includes:

- Hide Price in Portal
- Website Branding
- Operation Costs
  - Create a journal entry
""",

    'author': "Dimension3 Technology",
    'contributors': ['Juan Arcos juanparmer@gmail.com'],
    'website': "https://d-3system.com.au",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Website/Website',
    'version': '18.0.2.0.1',

    # any module necessary for this one to work correctly
    'depends': [
        'mail',
        # 'mrp_account',
        # 'sale_management',
        'web',
        'website',
        'website_sale'
    ],

    # always loaded
    'data': [
        'data/ir_cron_data.xml',
        'templates/sale_order_templates.xml',
        'templates/web_template.xml',
        'templates/website_templates.xml',
        'views/product_template_view.xml',
        'views/res_config_views.xml',
        'views/website_view.xml',
    ],
    
    # license
    'license': 'LGPL-3',
}
