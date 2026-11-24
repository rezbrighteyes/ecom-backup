import json

from markupsafe import Markup

from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def get_fb_advanced_match(self):
        """JSON for the <script type="application/json"> block in website.layout.

        Odoo 20 QWeb dropped t-raw (it now renders nothing), and t-out escapes a
        plain str to HTML entities, which a script element does not decode. So
        return Markup, with <, > and & escaped as JSON unicode escapes so a
        partner field can never close the script element.
        """
        name = self.name or ''
        parts = name.split()
        data = json.dumps({
            'em': self.email or '',
            'fn': parts[0] if parts else '',
            'ln': ' '.join(parts[1:]) if len(parts) > 1 else '',
            'ph': self.phone or '',
            'ct': self.city or '',
            'st': self.state_id.name if self.state_id else '',
            'zp': self.zip or '',
            'country': self.country_id.code if self.country_id else '',
        })
        data = data.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        return Markup(data)
