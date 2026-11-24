from odoo import SUPERUSER_ID, api

from odoo.addons.reza_rma.hooks import post_init_hook


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    post_init_hook(env)
