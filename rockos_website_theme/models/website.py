from odoo import api, fields, models


class Website(models.Model):
    _inherit = "website"

    rockos_facebook_url = fields.Char(string="Rockos Facebook URL")
    rockos_instagram_url = fields.Char(string="Rockos Instagram URL")
    rockos_phone = fields.Char(string="Rockos Phone")
    rockos_free_shipping_text = fields.Char(string="Rockos Free Shipping Text")

    @api.model
    def _rockos_setup_menu(self):
        from ..hooks import _scope_views_to_rockos, _seed_rockos_menu, _setup_rockos_pages

        website = self.sudo().search([("name", "=", "Rockos")], limit=1)
        if website:
            _scope_views_to_rockos(self.env, website)
            _seed_rockos_menu(self.env, website)
            _setup_rockos_pages(self.env, website)
        return True
