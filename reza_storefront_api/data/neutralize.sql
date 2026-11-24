-- An Odoo.sh staging/dev build restores the production database. The build
-- must not keep the production storefront token: without it the API answers
-- 404 there until someone sets a staging token on purpose.
DELETE FROM ir_config_parameter WHERE key = 'reza_storefront_api.token';
