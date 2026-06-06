from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    rockos_facebook_url = fields.Char(string="Rockos Facebook URL")
    rockos_instagram_url = fields.Char(string="Rockos Instagram URL")
    rockos_phone = fields.Char(string="Rockos Phone")
    rockos_free_shipping_text = fields.Char(string="Rockos Free Shipping Text")
