
from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    consider_all_related_warehouses = fields.Boolean()

    def _get_product_available_qty(self, product, **kwargs):
        if not self.consider_all_related_warehouses:
            return super()._get_product_available_qty(product, **kwargs)
        warehouses = self.env['stock.warehouse'].sudo().search([('company_id', 'in', self.company_id.parent_ids.ids)])
        return product.with_context(warehouse_id=warehouses.ids).free_qty
