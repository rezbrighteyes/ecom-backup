# -*- coding: utf-8 -*-

import logging
import xmlrpc.client

from odoo import fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class ExternalApi(models.TransientModel):
    _name = "external.api"
    _description = "External API"

    company_id = fields.Many2one(
        comodel_name="res.company", default=lambda self: self.env.company
    )

    company = fields.Integer(string="Company ID", default=1)
    companies = fields.Text()

    memory_error = fields.Boolean()

    state = fields.Selection(
        selection=[("draft", "Draft"), ("check", "Checked")], default="draft"
    )

    def action_external_api(self):
        url = self.company_id.external_api_url
        db = self.company_id.external_api_db
        username = self.company_id.external_api_username
        password = self.company_id.external_api_password

        try:
            common = xmlrpc.client.ServerProxy("{}/xmlrpc/2/common".format(url))
        except:
            print("Here")
        amodels = xmlrpc.client.ServerProxy("{}/xmlrpc/2/object".format(url))
        uid = common.authenticate(db, username, password, {})

        if not uid:
            raise ValidationError("Error on conection")

        return amodels, db, uid, password

    def action_external_check(self):
        amodels, db, uid, password = self.action_external_api()
        context = {"fields": ["name"]}
        res_companies = amodels.execute_kw(
            db, uid, password, "res.company", "search_read", [[]], context
        )

        companies = ""
        for company in res_companies:
            companies += f"ID: {company.get('id')}, Name: {company.get('name')}\n"

        self.write({"state": "check", "companies": companies})

        return self.action_act_window()

    def get_product_fields(self):
        return [
            "barcode",
            "default_code",
            "categ_id",
            "description",
            "description_ecommerce",
            "description_picking",
            "description_pickingin",
            "description_pickingout",
            "description_purchase",
            "description_sale",
            # "external_api",
            "image_1920",
            "list_price",
            "lst_price",
            "name",
            "product_tmpl_id",
            "product_template_variant_value_ids",
            # "product_variant_image_ids",
            "type",
            "uom_id",
            # "uom_po_id",
            "website_description",
            "website_meta_description",
        ]

    def get_template_vals(self, product_fields, product_vals):
        template_vals = {}
        for pfield in product_fields:
            template_vals.update({pfield: product_vals.get(pfield)})

        template_vals.pop("lst_price")
        template_vals.pop("product_tmpl_id")
        template_vals.pop('lst_price', None)
        template_vals.pop('barcode', None)
        template_vals.pop('list_price', None)
        template_vals.pop("product_template_variant_value_ids")
        # product_vals.pop("product_variant_image_ids")

        template_vals.update(
            {
                "uom_id": product_vals.get("uom_id")[0],
                # "uom_po_id": product_vals.get("uom_po_id")[0],
            }
        )

        return template_vals

    def get_product_vals(self, product_vals, product_dict):
        product_vals.update({"lst_price": product_dict.get("lst_price")})
        product_vals.pop('lst_price', None)
        product_vals.pop('list_price', None)
        return product_vals

    def action_product_product(self):
        Attribute = self.env["product.attribute"]
        Category = self.env["product.category"]
        Company = self.env["res.company"]
        Product = self.env["product.product"]
        Template = self.env["product.template"]
        Value = self.env["product.attribute.value"]

        company = Company.search(
            [("external_api", "=", True), ("external_api_product", "=", True)], limit=1
        )
        if not company:
            return False

        self = self.with_company(company)
        eapi = self.create({})

        amodels, db, uid, password = eapi.action_external_api()

        domain = [("type", "=", "consu")]
        if self.env.context.get("ea_create_date"):
            days = self.env.context.get("ea_create_date")
            create_date = fields.Datetime.add(fields.Datetime.now(), days=days)
            domain += [
                "|",
                ("create_date", ">=", create_date),
                ("write_date", ">=", create_date),
            ]
        product_fields = self.get_product_fields()
        context = {
            "fields": product_fields,
            "context": {"allowed_company_ids": [1]},
        }
        aproducts = amodels.execute_kw(
            db, uid, password, "product.product", "search_read", [domain], context
        )
        for aproduct in aproducts:
            product_vals = self.get_template_vals(product_fields, aproduct)

            # Category
            category_domain = [("display_name", "=", aproduct.get("categ_id")[1])]
            category = Category.search(category_domain, limit=1)
            if not category:
                category_name = aproduct.get("categ_id")[1].split("/")
                category = Category.create({"name": category_name[-1]})
            product_vals.update(categ_id=category.id)

            # Search
            product = Product.search(
                [("external_api_id", "=", aproduct.get("id"))], limit=1
            )
            # if aproduct.get("default_code") and not product:
            #     product = Product.search(
            #         [("default_code", "=", aproduct.get("default_code"))], limit=1
            #     )

            if product:
                if not product.external_api:
                    product_dict = self.get_product_vals(product_vals, aproduct)
                    product.write(product_dict)
                continue

            # Template
            template = Template.search(
                [("display_name", "=", aproduct.get("product_tmpl_id")[1])], limit=1
            )
            if not template:
                template = Template.create(product_vals)

            if not aproduct.get("product_template_variant_value_ids"):
                product_vals = {
                    "default_code": aproduct.get("default_code"),
                    "external_api_id": aproduct.get("id"),
                }
                product_dict = self.get_product_vals(product_vals, aproduct)
                product.write(product_dict)
                template.product_variant_ids[0].write(product_dict)
                amodels.execute_kw(
                    db,
                    uid,
                    password,
                    "product.product",
                    "write",
                    [aproduct.get("id"), {"external_api_id": product.id}],
                )
                continue

            # Attributes
            aattributes = amodels.execute_kw(
                db,
                uid,
                password,
                "product.template.attribute.value",
                "read",
                [aproduct.get("product_template_variant_value_ids")],
                {"fields": ["attribute_id", "product_attribute_value_id"]},
            )
            for aattribute in aattributes:
                # Attribute
                attribute = Attribute.search(
                    [("name", "=", aattribute.get("attribute_id")[1])], limit=1
                )
                if not attribute:
                    attribute = Attribute.create(
                        {
                            "name": aattribute.get("attribute_id")[1],
                            "create_variant": "always",
                        },
                    )
                # Value
                attribute_value = aattribute.get("product_attribute_value_id")
                value_name = attribute_value[1].split(": ")[-1]
                value = Value.search(
                    [
                        ("attribute_id", "=", attribute.id),
                        ("name", "=", value_name),
                    ],
                    limit=1,
                )
                if not value:
                    value = Value.create(
                        {
                            "attribute_id": attribute.id,
                            "name": value_name,
                        }
                    )

            line = template.attribute_line_ids.filtered(
                lambda l: l.attribute_id.id == attribute.id
            )
            if line:
                line.write({"value_ids": [(4, value.id, 0)]})
            else:
                # TODO
                # que pasa cuendo se creó despues
                line_vals = {"attribute_id": attribute.id, "value_ids": [value.id]}
                template.write({"attribute_line_ids": [(0, 0, line_vals)]})

            # Variants
            product = template.product_variant_ids.filtered(
                lambda p: attribute.id
                in p.product_template_variant_value_ids.attribute_id.ids
                and value.id
                in p.product_template_variant_value_ids.product_attribute_value_id.ids
            )
            if not product:
                product = template.product_variant_ids[-1]

            product_vals = {
                "default_code": aproduct.get("default_code"),
                "external_api_id": aproduct.get("id"),
            }
            product_dict = self.get_product_vals(product_vals, aproduct)
            product.write(product_dict)
            amodels.execute_kw(
                db,
                uid,
                password,
                "product.product",
                "write",
                [aproduct.get("id"), {"external_api_id": product.id}],
            )

        self.action_product_image()

        return True

    def action_product_image(self):
        Company = self.env["res.company"]
        Image = self.env["product.image"]
        Product = self.env["product.product"]
        Template = self.env["product.template"]

        company = Company.search(
            [("external_api", "=", True), ("external_api_product", "=", True)], limit=1
        )
        if not company:
            return False

        self = self.with_company(company)
        eapi = self.create({})

        amodels, db, uid, password = eapi.action_external_api()

        domain = [
            ("create_date", ">=", fields.Datetime.add(fields.Datetime.now(), days=-1))
        ]
        context = {
            "fields": ["name", "product_tmpl_id", "product_variant_id", "image_1920"],
            "context": {"allowed_company_ids": [1]},
        }
        aimages = amodels.execute_kw(
            db, uid, password, "product.image", "search_read", [domain], context
        )
        for aimage in aimages:
            image_vals = {
                "name": aimage.get("name"),
                "image_1920": aimage.get("image_1920"),
            }
            if aimage.get("product_variant_id"):
                product = Product.search(
                    [("external_api_id", "=", aimage.get("product_variant_id")[0])],
                    limit=1,
                )
                if product:
                    image_vals.update(product_variant_id=product.id)
            if aimage.get("product_tmpl_id"):
                template = Template.search(
                    [("display_name", "=", aimage.get("product_tmpl_id")[1])], limit=1
                )
                if template:
                    image_vals.update(product_tmpl_id=template.id)
            Image.create(image_vals)

        return True

    def action_stock_quant(self):
        Company = self.env["res.company"]
        Product = self.env["product.product"]
        Quant = self.env["stock.quant"]

        company = Company.search(
            [("external_api", "=", True), ("external_api_quant", "=", True)], limit=1
        )
        if not company:
            return False

        self.company_id = company

        self = self.with_company(company)
        eapi = self.create({})

        amodels, db, uid, password = eapi.action_external_api()

        domain = [("location_id.usage", "=", "internal")]
        context = {
            "fields": [
                "location_id",
                "product_id",
                "lot_id",
                "inventory_quantity_auto_apply",
                "quantity",
            ],
            # "context": {"allowed_company_ids": [1]},
        }
        aquants = amodels.execute_kw(
            db, uid, password, "stock.quant", "search_read", [domain], context
        )

        location_stock = self.env.ref("stock.stock_location_stock")
        location_company = company.external_api_location_id
        location = location_company or location_stock

        for aquant in aquants:
            product = Product.search(
                [("external_api_id", "=", aquant.get("product_id")[0])], limit=1
            )
            if not product:
                [aproduct] = amodels.execute_kw(
                    db,
                    uid,
                    password,
                    "product.product",
                    "read",
                    [aquant.get("product_id")[0]],
                    {"fields": ["default_code"]},
                )
                product = Product.search(
                    [("default_code", "=", aproduct.get("default_code"))], limit=1
                )
                if not product:
                    continue

            vals = {
                "location_id": location.id,
                "product_id": product.id,
                # "lot_id": product.id,
                # "inventory_quantity_auto_apply": aquant.get(
                #     "inventory_quantity_auto_apply"
                # ),
                # "quantity": aquant.get("quantity"),
                "inventory_quantity": aquant.get("quantity"),
                "owner_id": eapi.company_id.external_api_partner_id.id,
            }

            domain = [
                ("location_id", "=", location.id),
                ("product_id", "=", product.id),
                # ('lot_id','=',lot_id),
            ]
            quant = Quant.search(domain)

            if quant:
                quant.write(vals)
            else:
                quant = Quant.create(vals)
            quant.action_apply_inventory()

            # For products that have >5 on hand, mark them as continue selling & activate MTO or Reordering rules (min max is 0 and 0).
            # For products that have <5 on hand, prevent the sale (mark as out of stock) and turn off MTO or archive reordering rules.
            route = self.env.ref("stock.route_warehouse0_mto")
            tag = self.env.ref("d3_external_api.tag_external_api")

            quants = Quant.search(
                [
                    ("location_id.usage", "=", "internal"),
                    ("location_id", "=", location.id),
                    ("product_id.product_tag_ids", "not in", [tag.id]),
                ]
            )
            quantsl = quants.filtered(lambda q: q.quantity <= 5)
            quantsm = quants.filtered(lambda q: q.quantity > 5)
            quantsl.product_id.product_tmpl_id.write(
                {"allow_out_of_stock_order": False, "route_ids": [(3, route.id, 0)]}
            )
            quantsm.product_id.product_tmpl_id.write(
                {"allow_out_of_stock_order": True, "route_ids": [(4, route.id, 0)]}
            )

        return True
