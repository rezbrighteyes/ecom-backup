-- An Odoo.sh staging/dev build restores the production database. The build
-- must not keep the production storefront token: without it the API answers
-- 404 there until someone sets a staging token on purpose.
-- The Cloudflare Access settings go too: a staging host is not behind the
-- production Access application, so whoever opens staging on purpose sets
-- (or leaves unset) its own Access settings with its own token.
DELETE FROM ir_config_parameter WHERE key IN (
    'reza_storefront_api.token',
    'reza_storefront_api.access_team_domain',
    'reza_storefront_api.access_aud'
);
