
from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    def _get_product_available_qty(self, product, **kwargs):
        warehouses = self.env['stock.warehouse'].sudo().search([('company_id', 'in', self.company_id.parent_ids.ids)])
        return product.with_context(warehouse_id=warehouses.ids).free_qty
