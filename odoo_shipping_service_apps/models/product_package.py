# -*- coding: utf-8 -*-
#################################################################################
# Copyright (c) 2025-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################
import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)
Delivery = [
    ("none", "None"),
    ("fixed", "Fixed"),
    ("base_on_rule", "Base on Rule"),
    # ('fedex','fedex'),
    # ('ups','ups'),
    # ('usps','USPS'),
    # ('auspost','auspost'),
]


class product_package_line(models.Model):
    _name = "product.package.line"
    _description = "Product Package Line"

    order_line_id = fields.Many2one(comodel_name="sale.order.line", string="Order Line")
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
    )
    weight = fields.Float(
        default=0,
    )
    qty = fields.Float(
        default=1,
    )
    product_package_id = fields.Many2one(
        comodel_name="product.package", string="Package"
    )
    order_id = fields.Many2one(
        related="product_package_id.order_id",
    )

    @api.onchange("order_id")
    def onchage_order_id(self):
        return {
            "domain": {
                "product_id": [
                    ("id", "in", self.order_id.order_line.mapped("product_id.id"))
                ]
            }
        }

    @api.onchange("product_id")
    def onchage_product_id(self):
        default_product_weight = 0
        order_id = self.order_id
        if order_id:
            default_product_weight = order_id.carrier_id.default_product_weight
        self.weight = self.product_id.weight or default_product_weight


class product_package(models.Model):
    _name = "product.package"
    _description = "Product Package"

    complete_name = fields.Char(
        compute="_complete_name",
        string="Package Name",
    )
    packaging_id = fields.Many2one(
        comodel_name="stock.package.type", string="Packaging", required=False
    )
    order_id = fields.Many2one(comodel_name="sale.order")
    carrier_id = fields.Many2one(related="order_id.carrier_id")
    delivery_type = fields.Selection(selection=Delivery)
    full_capacity = fields.Boolean()
    eligible_quantity = fields.Boolean(
        string="Eligible Quantity", compute="_compute_eligible_quantity", store=True
    )
    package_id = fields.Many2one("stock.package", string="Package")
    pckage_id = fields.Many2one("stock.package", string="Quant Package")
    cover_amount = fields.Float(string="Cover Amount", default=0)
    qty = fields.Float(default=0)

    weight = fields.Float(string="Total Weight", compute="_compute_package_data")
    length = fields.Float(string="Package Length", compute="_compute_package_data")
    width = fields.Float(string="Package Width", compute="_compute_package_data")
    height = fields.Float(string="Package Height", compute="_compute_package_data")
    weight_uom_id = fields.Many2one(
        "uom.uom",
        string="Unit of Measure",
        readonly=True,
        help="Unit of Measure (Unit of Measure) is the unit of measurement for Weight",
        default=lambda self: self._default_uom,
    )
    package_line_ids = fields.One2many(
        "product.package.line", "product_package_id", string="Package Line"
    )
    quantity = fields.Integer(string="Quantity")
    product_id = fields.Many2one(
        comodel_name="product.product", string="Products", store=True
    )
    product_ids = fields.Many2many(
        comodel_name="product.product",
        compute="_compute_product_ids",
        string="Available Products",
    )
    order_line_id = fields.Many2one(
        comodel_name="sale.order.line", string="Order Lines", store=True
    )

    @api.model
    def default_get(self, fields=None):
        res = super(product_package, self).default_get(fields)
        if self._context.get("default_order_id"):
            res["order_id"] = self.env.context.get("default_order_id")
        return res

    @api.depends("order_id", "packaging_id")
    def _complete_name(self):
        for obj in self:
            name = obj.packaging_id.name
            if obj.order_id:
                name = obj.order_id.name + "[%s]" % (name)
            obj.complete_name = name

    @api.depends("package_line_ids")
    def _compute_qty_weight_cover_amount(self):
        for rec in self:
            package_line_ids = rec.package_line_ids
            default_product_weight = rec.carrier_id.default_product_weight
            packaging_id = rec.packaging_id
            cover_amount, qty, weight = 0, 0, 0
            for line_id in package_line_ids:
                lqty = line_id.qty
                qty += lqty
                order_line_id = line_id.order_line_id
                if order_line_id:
                    product_id = order_line_id.product_id
                    cover_amount += (
                        packaging_id.get_cover_amount(order_line_id.price_unit * lqty)
                        or 0
                    )
                    if product_id:
                        weight += (line_id.weight or default_product_weight) * lqty
            rec.cover_amount = cover_amount
            rec.weight = weight
            rec.qty = qty

    @api.model
    def _default_uom(self):
        uom_categ_id = self.env.ref("uom.product_uom_categ_kgm").id
        return self.env["uom.uom"].search(
            [("category_id", "=", uom_categ_id), ("factor", "=", 1)], limit=1
        )

    @api.depends(
        "quantity",
        "order_id.wk_packaging_ids.quantity",
        "order_id.order_line.product_uom_qty",
    )
    def _compute_eligible_quantity(self):
        for record in self:
            package_line_quantity = sum(
                rec.quantity
                for rec in record.order_id.wk_packaging_ids
                if rec.product_id == record.product_id
            )
            order_line_quantity = sum(
                rec.product_uom_qty
                for rec in record.order_id.order_line
                if rec.product_id == record.product_id
            )
            record.eligible_quantity = package_line_quantity > order_line_quantity

    @api.depends(
        "quantity",
        "product_id",
        "product_id.weight",
        "package_id",
        "packaging_id",
        "product_id.packaging_id",
    )
    def _compute_package_data(self):
        for rec in self:
            rec.weight = (rec.product_id.weight) * rec.quantity
            if rec.package_id:
                rec.weight += rec.package_id.shipping_weight
                rec.length = rec.package_id.length
                rec.width = rec.package_id.width
                rec.height = rec.package_id.height
                rec.cover_amount = rec.package_id.cover_amount
            elif rec.packaging_id:
                rec.weight += rec.packaging_id.base_weight
                rec.length = rec.packaging_id.packaging_length
                rec.width = rec.packaging_id.width
                rec.height = rec.packaging_id.height
                rec.cover_amount = rec.packaging_id.cover_amount

    @api.depends("order_id")
    def _compute_product_ids(self):
        for rec in self:
            if rec.order_id:
                products = rec.order_id.order_line.mapped("product_id")
                rec.product_ids = products
            else:
                rec.product_ids = False

    @api.onchange("pckage_id")
    def _onchange_pckage_id_set_packaging(self):
        if self.pckage_id:
            self.package_id = self.pckage_id
        else:
            self.package_id = self.product_id.packaging_id


class product_manual_package(models.Model):
    _name = "product.manual.package"
    _description = "Product Manual Package"

    eligible_quantity = fields.Boolean(
        string="Eligible Quantity", compute="_compute_eligible_quantity", store=True
    )

    quantity = fields.Integer(string="Quantity", default=1)
    product_id = fields.Many2one(
        comodel_name="product.product", string="Products", store=True
    )
    order_id = fields.Many2one(comodel_name="sale.order")
    product_ids = fields.Many2many(
        comodel_name="product.product",
        compute="_compute_product_ids",
        string="Available Products",
    )
    carrier_package_id = fields.Many2one(
        comodel_name="stock.package.type", string="Carrier Package"
    )
    product_package_id = fields.Many2one(
        "stock.package", string="Product Package"
    )
    package_id = fields.Many2one("stock.package", string="Package")
    weight = fields.Float(string="Total Weight", compute="_compute_package_data")
    length = fields.Float(string="Package Length", compute="_compute_package_data")
    width = fields.Float(string="Package Width", compute="_compute_package_data")
    height = fields.Float(string="Package Height", compute="_compute_package_data")
    cover_amount = fields.Float(string="Cover Amount", default=0)

    @api.depends(
        "quantity",
        "order_id.wk_manual_packaging_ids.quantity",
        "order_id.order_line.product_uom_qty",
    )
    def _compute_eligible_quantity(self):
        for record in self:
            package_line_quantity = sum(
                rec.quantity
                for rec in record.order_id.wk_manual_packaging_ids
                if rec.product_id == record.product_id
            )
            order_line_quantity = sum(
                rec.product_uom_qty
                for rec in record.order_id.order_line
                if rec.product_id == record.product_id
            )
            record.eligible_quantity = package_line_quantity > order_line_quantity

    @api.depends(
        "quantity",
        "product_id",
        "product_id.weight",
        "product_package_id",
        "carrier_package_id",
        "product_id.packaging_id",
    )
    def _compute_package_data(self):
        for rec in self:
            rec.weight = (rec.product_id.weight) * rec.quantity
            if rec.product_package_id:
                rec.weight += rec.product_package_id.shipping_weight
                rec.length = rec.product_package_id.length
                rec.width = rec.product_package_id.width
                rec.height = rec.product_package_id.height
                rec.cover_amount = rec.product_package_id.cover_amount
            elif rec.carrier_package_id:
                rec.weight += rec.carrier_package_id.base_weight
                rec.length = rec.carrier_package_id.packaging_length
                rec.width = rec.carrier_package_id.width
                rec.height = rec.carrier_package_id.height
                rec.cover_amount = rec.carrier_package_id.cover_amount

    @api.depends("order_id")
    def _compute_product_ids(self):
        for rec in self:
            if rec.order_id:
                products = rec.order_id.order_line.mapped("product_id")
                rec.product_ids = products
            else:
                rec.product_ids = False

    @api.onchange("product_id")
    def onchange_product(self):
        for rec in self:
            carrier_package = rec.order_id.carrier_id.packaging_type_id
            product_package = rec.product_id.packaging_id
            rec.carrier_package_id = carrier_package
            rec.product_package_id = product_package

    @api.onchange("package_id")
    def onchange_package_id(self):
        if self.package_id:
            self.product_package_id = self.package_id
        else:
            self.product_package_id = self.product_id.packaging_id
