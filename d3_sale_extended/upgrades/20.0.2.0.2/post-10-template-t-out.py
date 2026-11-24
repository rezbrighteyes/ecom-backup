# Odoo 20 QWeb no longer knows t-esc: it renders NOTHING (no error). This module
# overrides sale.mail_template_sale_confirmation, but that record is noupdate in
# `sale`, so a module upgrade does not rewrite its body from our data file and the
# stored 18 body keeps t-esc -- the order email would lose product name, variant
# details and quantity. t-out escapes exactly like t-esc did, so rewrite it in
# every stored language.
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT res_id FROM ir_model_data
         WHERE module = 'sale' AND name = 'mail_template_sale_confirmation'
           AND model = 'mail.template'
        """
    )
    row = cr.fetchone()
    if not row:
        return
    cr.execute(
        """
        UPDATE mail_template
           SET body_html = (
                SELECT jsonb_object_agg(key, replace(value, 't-esc=', 't-out='))
                  FROM jsonb_each_text(body_html)
           )
         WHERE id = %s AND body_html::text LIKE '%%t-esc=%%'
        """,
        [row[0]],
    )
    _logger.info("d3_sale_extended: t-esc -> t-out in sale.mail_template_sale_confirmation (%s row)", cr.rowcount)
