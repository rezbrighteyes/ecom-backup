# -*- coding: utf-8 -*-
#################################################################################
##    Copyright (c) 2025-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
#    You should have received a copy of the License along with this program.
#    If not, see <https://store.webkul.com/license.html/>
#################################################################################
from collections import Counter
from datetime import datetime, timedelta
from odoo.tools import float_is_zero, float_compare, DEFAULT_SERVER_DATETIME_FORMAT
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError  ##Warning
import logging

_logger = logging.getLogger(__name__)
Delivery = [
    ("none", "None"),
    ("fixed", "Fixed"),
    ("base_on_rule", "Base on Rule"),
]


class ProductTemplate(models.Model):
    _inherit = "product.template"
    wk_packaging_ids = fields.Many2many(
        "stock.package.type",
        "product_tmp_package_type_rel",
        "product_tmpl_id",
        "package_type_id",
        string="Packaging",
    )


class SaleOrder(models.Model):
    _inherit = "sale.order"
    carrier_price = fields.Float(
        string="Actual Carrier Charges", help="Actual Carrier Charges recive from api "
    )
    multi_package = fields.Boolean(
        string="Multi Package",
        help="compute from delivery carrier'",
        compute="_compute_multi_package",store=False
    )
    packaging_type_all_product = fields.Boolean(
        string="All Product one Package",
        help="compute from delivery carrier'",
        compute="_compute_packaging_type_all_product",
    )
    delivery_type = fields.Selection(related="carrier_id.delivery_type", readonly=True)

    create_package = fields.Selection(
        string="Create Package",
        selection=[("auto", "Automatic"), ("manual", "Manual")],
        default="auto",
        help="Create  automatic package as per packing max weight limit and  max qty  ",
    )
    wk_packaging_ids = fields.One2many(
        comodel_name="product.package",
        inverse_name="order_id",
        string="Automatic Packages",
    )
    wk_manual_packaging_ids = fields.One2many(
        comodel_name="product.manual.package",
        inverse_name="order_id",
        string="Manual Packages",
    )
    qunant_package_id = fields.Many2one(
        comodel_name="stock.package", string="Quant Packge"
    )
    package_id = fields.Many2one("stock.package", string="Package")

    @api.onchange("package_id")
    def _onchange_package_type_id(self):
        for order in self:
            packages = self.env["product.package"].search([("order_id", "=", order.id)])
            for package in packages:
                package.package_id = (
                    order.package_id.id if order.package_id.packaging_id else False
                )

    @api.depends("create_package")
    def _compute_packaging_type_all_product(self):
        if self.create_package == "auto":
            carrier = self.carrier_id.package_creation_type == "all_products"
            self.packaging_type_all_product = True if carrier else False
        else:
            self.packaging_type_all_product = False

    def _compute_multi_package(self):
        multi_package = self.env["delivery.carrier"].search(
            [("multi_package", "=", True)], limit=1
        )
        self.multi_package = True if multi_package.multi_package else False

    def auto_create_package(self):
        obj = self.filtered(lambda o: o.carrier_id)
        no_carrier = self - obj
        if len(no_carrier):
            raise ValidationError(
                "Select Delivery Method For %s ." % (no_carrier.mapped("name"))
            )
        for order in obj:
            order.carrier_id.wk_set_order_package(order)
        return True

    @api.model
    def wk_get_order_package(self):
        return map(
            lambda wk_packaging_id: dict(
                packaging_id=wk_packaging_id.packaging_id.id,
                weight=wk_packaging_id.weight,
                width=wk_packaging_id.width,
                length=wk_packaging_id.length,
                height=wk_packaging_id.height,
                cover_amount=wk_packaging_id.cover_amount,
                qty=wk_packaging_id.qty,
            ),
            self.wk_packaging_ids,
        )

    def _wk_check_carrier_quotation(self, force_carrier_id=None):
        res = True

        try:
            ctx = dict(self._context)
            ctx["wk_website"] = 1
            res = self.with_context(ctx)._check_carrier_quotation(force_carrier_id)
        except Exception as e:
            _logger.error("Checking carrier quotation #%s" % e)
            res = False
        return res

    def generate_sale_packages(self):
        for order in self:
            carrier = order.carrier_id
            default_packaging = carrier.packaging_type_id
            creation_type = carrier.package_creation_type
            if creation_type and default_packaging:
                lines = order.order_line.filtered(
                    lambda l: l.product_id.type != "service"
                )
                for line in lines:
                    product = line.product_id
                    qty = int(line.product_uom_qty)
                    packaging = default_packaging
                    if not packaging:
                        continue
                    if creation_type == "per_line":
                        existing_packages = order.wk_packaging_ids.filtered(
                            lambda p: p.product_id.id == product.id
                            and p.order_line_id == line
                        )
                        if existing_packages:
                            primary_package = existing_packages[0]
                            primary_package.write({"quantity": qty})
                            extra_packages = existing_packages[1:]
                            if extra_packages:
                                extra_packages.unlink()
                        else:
                            self.env["product.package"].create(
                                {
                                    "order_id": order.id,
                                    "product_id": product.id,
                                    "packaging_id": packaging.id,
                                    "quantity": qty,
                                    "package_id": product.packaging_id.id,
                                    "order_line_id": line.id,
                                }
                            )
                    elif creation_type == "per_qty":
                        existing_packages = self.env["product.package"].search(
                            [
                                ("order_id", "=", order.id),
                                ("order_line_id", "=", line.id),
                                ("product_id", "=", product.id),
                            ]
                        )
                        existing_packages.write({"quantity": 1})
                        existing_count = len(existing_packages)
                        if qty > existing_count:
                            for _ in range(qty - existing_count):
                                self.env["product.package"].create(
                                    {
                                        "order_id": order.id,
                                        "order_line_id": line.id,
                                        "product_id": product.id,
                                        "packaging_id": packaging.id,
                                        "quantity": 1,
                                        "package_id": product.packaging_id.id,
                                    }
                                )
                        elif qty < existing_count:
                            packages_to_remove = existing_packages[
                                : existing_count - qty
                            ]
                            packages_to_remove.unlink()
            else:
                raise ValidationError(
                    "Select a delivery carrier that supports multiple packages, along with the desired packaging type and packaging.\nInstruction :-> \n1. Choose a carrier that supports multi-package delivery\n2. Select the packaging type.\n3. Select the specific packaging."
                )
