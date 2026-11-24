# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

import werkzeug

class WebsiteSaleMultiWebsite(WebsiteSale):

    # Odoo 20 port: request.website is gone (use request.env.website), and the
    # core signature is product(self, product, pricelist=None, **kwargs) --
    # category/search now arrive in kwargs, so pass everything through.
    @http.route()
    def product(self, product, **kwargs):

        if product and product.website_ids and request.env.website not in product.website_ids:
            raise werkzeug.exceptions.NotFound()
        return super(WebsiteSaleMultiWebsite, self).product(product, **kwargs)
