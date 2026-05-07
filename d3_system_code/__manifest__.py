# -*- coding: utf-8 -*-
{
    'name': "D3 System Code",

    'summary': "System Code",

    'description': """
        Adds a "D3 System Settings" section to select and install D3 suite modules.
    """,

    'author': "d-3systems",
    'website': "https://d-3system.com.au/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Setting',
    'version': '18.0.1.0.0',

    # any module necessary for this one to work correctly
    'depends': ['base'],
    'assets': {
        'web.assets_backend': [
            'd3_system_code/static/description/*',
        ],
     },
    # always loaded
    'data': [
        # 'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
    ],

    # license
    'license': 'OPL-1',
}
