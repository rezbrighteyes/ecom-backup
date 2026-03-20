# -*- coding: utf-8 -*-
#################################################################################
#
#    Copyright (c) 2025-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################
from odoo import models, fields

class ProductProduct(models.Model):
    _inherit = "product.product"

    packaging_id = fields.Many2one("stock.package", string="Default Packages")
