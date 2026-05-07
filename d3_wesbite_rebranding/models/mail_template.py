# -*- coding: utf-8 -*-

from bs4 import BeautifulSoup

from odoo import models


class MailTemplate(models.Model):
    _inherit = 'mail.template'

    def run_website_branding(self):
        templates = self.search([('body_html', 'ilike', 'Powered by')])
        for template in templates:
            body_html = template.body_html

            # body_html = body_html.replace('Powered by', '<!-- Powered by')
            # body_html = body_html.replace('Odoo</a>', 'Odoo</a> -->')

            soup = BeautifulSoup(body_html, 'lxml')
            rows = soup.find_all('tr')
            for row in rows:
                if 'Powered by' in row.get_text():
                    row.decompose()

            template.write({'body_html': str(soup)})
