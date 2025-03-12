# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.


from . import models
from . import wizard
from . import controllers

from odoo import api, SUPERUSER_ID


# def _assign_default_website_ids(cr, registry):
#     env = api.Environment(cr, SUPERUSER_ID, {})
#     product_ids = env["product.template"].search([
#         ("website_id", "!=", False)
#     ])
#     if product_ids:
#         for product in product_ids:
#             product.write({
#                 "website_ids": [(6, 0, product.website_id.ids)],
#             })

def _assign_default_website_ids(env):
    #env = api.Environment(cr, SUPERUSER_ID, {})
    product_ids = env["product.template"].search([
        ("website_id", "!=", False)
    ])
    if product_ids:
        for product in product_ids:
            product.write({
                "website_ids": [(6, 0, product.website_id.ids)],
            })