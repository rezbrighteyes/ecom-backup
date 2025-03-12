# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
{
    "name": "Product Multi Website",
    "author": "Softhealer Technologies",
    "website": "http://www.softhealer.com",
    "support": "support@softhealer.com",
    "category": "Website",
    "license": "OPL-1",
    "summary": """
Manage Multi Website For Products Set Product For Specific Website
Multiple Website Per Product Multi Website For Every Product
Set Websites Specific Product Module, Set Multiple Website Odoo
""",
    "description": """
Sometimes we have to manage products for more than one website.
This module helps to set multiple websites for each product.
You can configure multi-website per product in a single click.
You can manage multi-website under a single menu.
We provide a mass update feature for multiple websites also,
so you can update the multi-product for multi-website quickly.
""",
    "version": "0.0.2",
    "depends": [
        "website_sale"
    ],
    "application": True,
    "data": [
        "security/ir.model.access.csv",
        "views/product_views.xml",
        "wizard/sh_product_multi_website_wizard_views.xml",
    ],
    "images": ["static/description/background.png", ],
    "auto_install": False,
    "installable": True,
    "post_init_hook": "_assign_default_website_ids",
    "price": 45,
    "currency": "EUR"
}
