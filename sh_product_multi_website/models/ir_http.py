# -*- coding: utf-8 -*-
# Copyright (C) Softhealer Technologies
from odoo import models

from odoo.addons.website.models import ir_http
from odoo.tools.safe_eval import safe_eval

class ShModelConverter(ir_http.ModelConverter):
    

    def generate(self, env, args, dom=None):
        """
            Override by Softhealer Technologies
        """
        Model = env[self.model]

        # Softhealer Custom code
        #  replace website domain to multiple website domain.
        if hasattr(Model,"website_ids") and "website_ids" in Model._fields:
            self.domain ="['|',('website_ids','=',False),('website_ids','=',current_website_id)]"
        # Softhealer Custom code
            
        # Allow to current_website_id directly in route domain
        args['current_website_id'] = env['website'].get_current_website().id
        domain = safe_eval(self.domain, args)
        if dom:
            domain += dom
        for record in Model.search(domain):
            # return record so URL will be the real endpoint URL as the record will go through `slug()`
            # the same way as endpoint URL is retrieved during dispatch (301 redirect), see `to_url()` from ModelConverter
            yield record

class ShHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_converters(cls):
        """ 
            Override by Softhealer Technologies
            update the converters model: ModelConverter to new ShModelConverter
        """
        return dict(super()._get_converters(),model=ShModelConverter)
    