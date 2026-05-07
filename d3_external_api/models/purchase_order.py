# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    external_api = fields.Boolean("No Sync", copy=False)
    external_api_purchase = fields.Boolean(related="company_id.external_api_purchase")
    external_api_sale = fields.Integer("Dest. Sale", copy=False)

    def button_confirm(self):
        res = super(PurchaseOrder, self).button_confirm()
        purchases = self.filtered("external_api")
        purchases.get_external_api_sale()
        return res

    def button_cancel(self):
        res = super(PurchaseOrder, self).button_cancel()
        purchases = self.filtered("external_api")
        purchases.cancel_external_api_sale()
        return res

    def button_draft(self):
        res = super(PurchaseOrder, self).button_draft()
        purchases = self.filtered("external_api")
        purchases.draft_external_api_sale()
        return res

    def action_create_invoice(self):
        res = super(PurchaseOrder, self).action_create_invoice()
        purchases = self.filtered("external_api")
        purchases.invoice_external_api_sale()
        return res

    def get_external_api_sale(self):
        for purchase in self.filtered("external_api"):
            Eapi = self.env["external.api"]
            eapi = Eapi.create({'company_id': purchase.company_id.id})
            emodels, db, uid, password = eapi.action_external_api()

            if purchase.external_api_sale:
                purchase.confirm_external_api_sale()
                continue
            company = purchase.company_id
            vals = {
                "partner_id": company.external_api_purchase_partner,
                # "order_line": purchase.get_external_api_sale_line(),
                "client_order_ref": purchase.name,
            }
            context = {"context": {"allowed_company_ids": [1]}}
            sale = emodels.execute_kw(
                db, uid, password, "sale.order", "create", [vals], context
            )
            purchase.external_api_sale = sale
            purchase.get_external_api_sale_line(self.order_line)
            emodels.execute_kw(
                db, uid, password, "sale.order", "action_confirm", [sale], context
            )
            [saleo] = emodels.execute_kw(
                db,
                uid,
                password,
                "sale.order",
                "read",
                [sale],
                {"fields": ["picking_ids"]},
            )
            spicking = emodels.execute_kw(
                db,
                uid,
                password,
                "stock.picking",
                "read",
                [saleo.get("picking_ids")],
                {"fields": ["state"]},
            )
            if spicking and spicking[0].get("state") == "assigned":
                res = emodels.execute_kw(
                    db,
                    uid,
                    password,
                    "stock.picking",
                    "button_validate",
                    [spicking[0].get("id")],
                    context,
                )
                if res is True:
                    purchase.picking_ids.button_validate()
        return True

    def get_external_api_sale_line(self, lines):
        if not lines:
            return False
        Eapi = self.env["external.api"]
        eapi = Eapi.create({'company_id': self.company_id.id})
        emodels, db, uid, password = eapi.action_external_api()
        for line in lines:
            if not line.product_id.external_api_id:
                continue
            vals = {
                "product_id": line.product_id.external_api_id,
                "name": line.product_id.display_name,
                "product_uom_qty": line.product_qty,
                "product_uom_id": line.product_uom.id,
                "price_unit": line.price_unit,
                "discount": line.discount,
                "order_id": self.external_api_sale,
            }
            context = {"context": {"allowed_company_ids": [1]}}
            sline = emodels.execute_kw(
                db, uid, password, "sale.order.line", "create", [vals], context
            )
            line.external_api_line = sline

    def confirm_external_api_sale(self):
        Eapi = self.env["external.api"]
        eapi = Eapi.create({'company_id': self.company_id.id})
        emodels, db, uid, password = eapi.action_external_api()
        context = {"context": {"allowed_company_ids": [1]}}
        purchases = self.filtered("external_api_sale")
        sale_ids = purchases.mapped("external_api_sale")
        emodels.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "action_confirm",
            [sale_ids],
            context,
        )
        return True

    def cancel_external_api_sale(self):
        purchases = self.filtered("external_api_sale")
        if not purchases:
            return False

        Eapi = self.env["external.api"]
        eapi = Eapi.create({'company_id': self.company_id.id})
        emodels, db, uid, password = eapi.action_external_api()
        context = {
            "context": {"allowed_company_ids": [1], "disable_cancel_warning": True}
        }
        sale_ids = purchases.mapped("external_api_sale")
        emodels.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "action_cancel",
            [sale_ids],
            context,
        )
        return True

    def draft_external_api_sale(self):
        Eapi = self.env["external.api"]
        eapi = Eapi.create({'company_id': self.company_id.id})
        emodels, db, uid, password = eapi.action_external_api()
        context = {"context": {"allowed_company_ids": [1]}}
        purchases = self.filtered("external_api_sale")
        sale_ids = purchases.mapped("external_api_sale")
        emodels.execute_kw(
            db,
            uid,
            password,
            "sale.order",
            "action_draft",
            [sale_ids],
            context,
        )
        return True

    def invoice_external_api_sale(self):
        Eapi = self.env["external.api"]
        eapi = Eapi.create({'company_id': self.company_id.id})
        emodels, db, uid, password = eapi.action_external_api()

        # active_ids=sale_order.ids
        # active_id=sale_order.id

        purchases = self.filtered("external_api_sale")
        sale_ids = purchases.mapped("external_api_sale")

        context = {"context": {"allowed_company_ids": [1], "active_ids": sale_ids}}

        inv = emodels.execute_kw(
            db,
            uid,
            password,
            "sale.advance.payment.inv",
            "create",
            # [{"sale_order_ids": [(4, sale, 0) for sale in sale_ids]}],
            [{}],
            context,
        )

        try:
            emodels.execute_kw(
                db,
                uid,
                password,
                "sale.advance.payment.inv",
                "create_invoices",
                [inv],
                context,
            )
        except:
            return False

        return True


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    external_api = fields.Boolean(related="order_id.external_api")
    external_api_line = fields.Integer("Dest. Line", copy=False)

    @api.model_create_multi
    def create(self, vals):
        lines = super(PurchaseOrderLine, self).create(vals)
        olines = lines.filtered(
            lambda l: l.order_id
            and l.order_id.state in ("purchase", "done")
            and l.external_api
            and l.product_id
            and l.product_id.external_api_id
        )
        if not olines:
            return lines
        purchases = olines.order_id
        for purchase in purchases:
            plines = olines.filtered(lambda l: l.order_id.id == purchase.id)
            purchase.get_external_api_sale_line(plines)
        olines.get_external_api_move()
        return lines

    def write(self, vals):
        res = super(PurchaseOrderLine, self).write(vals)
        if vals.get("product_qty"):
            lines = self.filtered(
                lambda l: l.order_id
                and l.order_id.state in ("purchase", "done")
                and l.external_api
                and l.product_id
                and l.product_id.external_api_id
                and l.external_api_line
            )

            if not lines:
                return res

            Eapi = self.env["external.api"]
            eapi = Eapi.create({'company_id': self.company_id.id})
            emodels, db, uid, password = eapi.action_external_api()
            context = {"context": {"allowed_company_ids": [1]}}

            for line in lines:
                lvals = {"product_uom_qty": vals.get("product_qty")}
                emodels.execute_kw(
                    db,
                    uid,
                    password,
                    "sale.order.line",
                    "write",
                    [line.external_api_line, lvals],
                    context,
                )
            lines.get_external_api_move()
        return res

    def get_external_api_move(self):
        Eapi = self.env["external.api"]
        eapi = Eapi.create({'company_id': self.company_id.id})
        emodels, db, uid, password = eapi.action_external_api()
        for line in self.filtered("external_api_line"):
            [sline] = emodels.execute_kw(
                db,
                uid,
                password,
                "sale.order.line",
                "read",
                [line.external_api_line],
                {"fields": ["move_ids"]},
            )
            moves = emodels.execute_kw(
                db,
                uid,
                password,
                "stock.move",
                "read",
                [sline.get("move_ids")],
                {"fields": ["picking_id", "state"]},
            )
            for move in moves:
                if move.get("state") != "assigned":
                    continue
                res = emodels.execute_kw(
                    db,
                    uid,
                    password,
                    "stock.picking",
                    "button_validate",
                    [move.get("picking_id")[0]],
                )
                if res is True:
                    line.move_ids.filtered(
                        lambda m: m.state == "assigned"
                    ).picking_id.button_validate()
        return True
