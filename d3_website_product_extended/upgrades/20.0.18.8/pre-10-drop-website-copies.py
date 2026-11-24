"""Delete the website-specific copies of this module's views.

Production holds 10 of them (spec filters x5, spec filters offcanvas x2,
variant picker x3), saved by the website editor on Odoo 18. A module update
never rewrites a copy, so they would keep Odoo 18 xpaths into templates that
Odoo 20 restructured (product_variants is deleted, the filter sidebar moved
into product_attribute_filters_form) and break or blank the shop. They hold
no editor content of their own: the module's views are pure xpath patches.

Copies are told apart from the module's own views by having no
ir_model_data row. Views inheriting from a copy go too.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        WITH RECURSIVE doomed AS (
            SELECT v.id
              FROM ir_ui_view v
             WHERE v.key LIKE 'd3\\_website\\_product\\_extended.%%'
               AND v.website_id IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM ir_model_data d
                                WHERE d.model = 'ir.ui.view' AND d.res_id = v.id)
            UNION
            SELECT c.id FROM ir_ui_view c JOIN doomed p ON c.inherit_id = p.id
        )
        DELETE FROM ir_ui_view WHERE id IN (SELECT id FROM doomed)
        RETURNING id
    """)
    ids = [r[0] for r in cr.fetchall()]
    _logger.info("d3_website_product_extended: deleted %s website view copies: %s", len(ids), ids)
