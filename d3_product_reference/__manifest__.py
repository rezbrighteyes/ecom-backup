# -*- coding: utf-8 -*-
{
    'name': "D3 Product Reference",

    'summary': "Product Second Reference",

    'description': """
        A new field, "Second Reference," has been added to the products. \n
        Users can search for products using this additional reference field.
    """,

    'author': "d-3systems",
    'contribuitors': ["Juan Arcos juanparmer@gmail.com"],
    'website': "https://d-3system.com.au/",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Sales/Sales',
    'version': '18.0.0.0.1',

    # any module necessary for this one to work correctly
    'depends': ['product'],

    # always loaded
    'data': [
        'views/product_product_views.xml',
        'views/product_template_views.xml',
    ],

    # license
    'license': 'OPL-1',
}

