# -*- coding: utf-8 -*-

from odoo import api, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    @api.model_create_multi
    def create(self, vals):
        Order = self.env["sale.order"]
        pickings = super(StockPicking, self).create(vals)
        for picking in pickings.filtered("origin"):
            order = Order.search([("name", "=", picking.origin)])
            if not order or not order.picking_note:
                continue
            if order.picking_note == picking.note:
                continue
            if not picking.note:
                note = order.picking_note
            else:
                note = picking.note + order.picking_note
            picking.note = note
        return pickings
