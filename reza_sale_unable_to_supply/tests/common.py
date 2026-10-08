# -*- coding: utf-8 -*-
from odoo import Command
from odoo.tests import TransactionCase, new_test_user


class UtsCommon(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        # The April database copy holds the company's bank account untrusted,
        # and posting an invoice then raises RedirectWarning. Production posts
        # invoices fine, so trust it inside the test transaction only.
        cls.company.partner_id.bank_ids.allow_out_payment = True
        cls.user = new_test_user(
            cls.env, login="reza_uts_staff",
            groups="sales_team.group_sale_manager,account.group_account_invoice,stock.group_stock_user",
            company_id=cls.company.id, company_ids=[cls.company.id],
        )
        cls.partner = cls.env["res.partner"].create({"name": "UTS Customer"})
        cls.tax = cls.env["account.tax"].create({
            "name": "UTS 10% incl",
            "amount": 10.0,
            "type_tax_use": "sale",
            "price_include_override": "tax_included",
            "company_id": cls.company.id,
        })
        Product = cls.env["product.product"]
        cls.nobbies = Product.create({
            "name": "UTS Nobbies", "type": "consu", "is_storable": True,
            "list_price": 24.99, "invoice_policy": "order", "taxes_id": [Command.set(cls.tax.ids)],
        })
        cls.thongs = Product.create({
            "name": "UTS Thongs", "type": "consu", "is_storable": True,
            "list_price": 22.99, "invoice_policy": "order", "taxes_id": [Command.set(cls.tax.ids)],
        })
        cls.shipping = Product.create({
            "name": "UTS Parcel Post", "type": "service",
            "list_price": 12.50, "invoice_policy": "order", "taxes_id": [Command.clear()],
        })

    # ----------------------------------------------------------------- helpers
    def _order(self, lines=None, confirm=True):
        lines = lines or [(self.nobbies, 1, 24.99), (self.thongs, 1, 22.99), (self.shipping, 1, 12.50)]
        order = self.env["sale.order"].with_user(self.user).create({
            "partner_id": self.partner.id,
            "order_line": [
                Command.create({"product_id": p.id, "product_uom_qty": q, "price_unit": price})
                for p, q, price in lines
            ],
        })
        if confirm:
            order.action_confirm()
        return order

    def _invoice(self, order):
        invoice = order._create_invoices()
        invoice.action_post()
        return invoice

    def _line(self, order, product):
        return order.order_line.filtered(lambda l: l.product_id == product)

    def _apply(self, order, qtys, user=None):
        wizard = self.env["reza.unable.supply.wizard"].with_user(user or self.user).with_context(
            default_order_id=order.id).create({})
        for wl in wizard.line_ids:
            wl.qty_to_remove = qtys.get(wl.sale_line_id.product_id, 0.0)
        return wizard.action_apply()

    def _refunds(self, order):
        return order.order_line.invoice_lines.move_id.filtered(lambda m: m.move_type == "out_refund")

