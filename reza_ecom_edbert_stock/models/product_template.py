# -*- coding: utf-8 -*-

from odoo import api, fields, models

from .product_product import INTERNAL_ONLY


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Named "total" rather than repeating the variant field's name. Because
    # product.product _inherits product.template, a same-named field on both
    # models means a variant answers a variant question and a template answers
    # a template question through what looks like one field. The count below is
    # not shadowed at all, so the pair would read as if they matched when they
    # do not.
    reza_edbert_total_free_qty = fields.Float(
        string="Edbert Free Qty (all variants)",
        digits="Product Unit",
        compute="_compute_reza_edbert_stock",
        store=True,
        groups=INTERNAL_ONLY,
        help="Total free quantity Edbert holds across every variant of this "
        "product. A variant that could not be matched contributes nothing, so "
        "read this figure together with the unmatched count beside it.",
    )

    reza_edbert_unmatched_count = fields.Integer(
        string="Edbert Unmatched Variants",
        compute="_compute_reza_edbert_stock",
        store=True,
        groups=INTERNAL_ONLY,
        help="How many variants of this product could not be matched to an "
        "Edbert product. Anything above zero means the total beside it is "
        "short, because those variants report nothing rather than zero.",
    )

    # Defined on the variant too, which shadows this one there. That is the
    # same shadowing the total above was renamed to avoid, and it is allowed
    # here on purpose: both computes read one global timestamp and return the
    # identical value, so which model answers cannot matter. The total could
    # not say that -- a variant figure and a sum are different numbers.
    reza_edbert_last_sync = fields.Datetime(
        string="Edbert Last Checked",
        compute="_compute_reza_edbert_last_sync",
        groups=INTERNAL_ONLY,
        help="When the whole catalogue was last checked against Edbert.",
    )

    @api.depends(
        "product_variant_ids.reza_edbert_free_qty",
        "product_variant_ids.reza_edbert_stock_state",
    )
    def _compute_reza_edbert_stock(self):
        for template in self:
            variants = template.product_variant_ids
            template.reza_edbert_total_free_qty = sum(
                variants.mapped("reza_edbert_free_qty")
            )
            template.reza_edbert_unmatched_count = len(
                variants.filtered(lambda v: v.reza_edbert_stock_state != "ok")
            )

    def _compute_reza_edbert_last_sync(self):
        value = self.env["reza.edbert.stock.sync"]._last_sync()
        for template in self:
            template.reza_edbert_last_sync = value
