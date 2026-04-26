import json
from odoo import models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def get_fb_advanced_match(self):
        name = self.name or ''
        parts = name.split()
        return json.dumps({
            'em': self.email or '',
            'fn': parts[0] if parts else '',
            'ln': ' '.join(parts[1:]) if len(parts) > 1 else '',
            'ph': self.phone or '',
            'ct': self.city or '',
            'st': self.state_id.name if self.state_id else '',
            'zp': self.zip or '',
            'country': self.country_id.code if self.country_id else '',
        })
