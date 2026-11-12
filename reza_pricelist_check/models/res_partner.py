# -*- coding: utf-8 -*-
from odoo import _, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_reza_check_prices(self):
        """Check Prices for the list this customer is on in the current company.

        Reads the backend pricelist (what a quotation raised here uses), in
        the active company, because the field is company-dependent.
        """
        self.ensure_one()
        partner = self.commercial_partner_id.with_company(self.env.company)
        pricelist = partner.property_product_pricelist
        if not pricelist:
            raise UserError(_("%s has no price list in %s.", partner.display_name, self.env.company.name))
        return pricelist.action_reza_check_prices()
