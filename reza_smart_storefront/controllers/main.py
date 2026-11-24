from odoo import http
from odoo.http import request


class DriftKartLanding(http.Controller):

    @http.route('/drift-kart', type='http', auth='public', website=True)
    def drift_kart_landing(self, **kwargs):
        website = request.env.website
        if website.name != 'WhatYouNeed':
            return request.redirect('/')
        return request.render('reza_smart_storefront.drift_kart_landing_page', {})
