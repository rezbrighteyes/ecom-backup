# -*- coding: utf-8 -*-
{
    'name': " d3 Website Rebranding",

    'summary': "Website Branding Override",

    'description': """
Website Branding Override
This module customizes the default Odoo website branding message by replacing the Odoo logo and link with your company’s logo and URL. 
It also updates the final message displayed in the footer to include your brand name.
    """,

    'author': "d-3system",
    'website': "https://d-3system.com.au/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Website/Website',
    'version': '20.0.1.0.0',

    # any module necessary for this one to work correctly
    'depends': [
        'website_sale'
    ],

    # always loaded
    'data': [
        'data/ir_cron_data.xml',
        'templates/web_template.xml',
        'templates/website_templates.xml',
    ],

    # license
    'license': 'OPL-1'
}

