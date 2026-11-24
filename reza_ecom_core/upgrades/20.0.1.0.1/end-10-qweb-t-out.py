"""Odoo 20 renders NOTHING for `t-esc` and `t-raw` (no error): only `t-out`
works. The upgrade regenerates Odoo's own views, but database-only copies
keep their old arch: website-specific (COW) views, Studio views, edited
email templates. Rewrite every leftover in every stored language.

Runs in the END phase, after every module is updated, so the views that the
modules reload are already final. `t-out` escapes a str and passes Markup
through, which is what `t-esc` and `t-raw` (on Markup) did on 18.
"""
import json
import logging
import re

_logger = logging.getLogger(__name__)

PATTERN = re.compile(r"\bt-(esc|raw)=")


def _rewrite_jsonb(cr, table, column):
    cr.execute(
        f"SELECT id, {column} FROM {table} "
        f"WHERE {column}::text ~ 't-(esc|raw)='"
    )
    changed = 0
    for rec_id, value in cr.fetchall():
        if not value:
            continue
        new = {lang: PATTERN.sub("t-out=", text) if isinstance(text, str) else text
               for lang, text in value.items()}
        if new != value:
            cr.execute(f"UPDATE {table} SET {column} = %s::jsonb WHERE id = %s",
                       [json.dumps(new), rec_id])
            changed += 1
    return changed


def migrate(cr, version):
    views = _rewrite_jsonb(cr, "ir_ui_view", "arch_db")
    templates = _rewrite_jsonb(cr, "mail_template", "body_html")
    _logger.info("reza_ecom_core: t-esc/t-raw -> t-out in %s views and %s mail templates",
                 views, templates)
