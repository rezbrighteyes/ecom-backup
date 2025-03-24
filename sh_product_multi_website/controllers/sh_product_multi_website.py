# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

import werkzeug

class WebsiteSaleMultiWebsite(WebsiteSale):

    @http.route()
    def product(self, product, category='', search='', **kwargs):

        if product and product.website_ids and request.website.id not in product.website_ids.ids:
            raise werkzeug.exceptions.NotFound()
        return super(WebsiteSaleMultiWebsite, self).product(product = product,category=category, search=search, **kwargs)
