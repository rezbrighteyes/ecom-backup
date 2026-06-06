# Rockos Website Theme

This module creates an Odoo company branch named `Rockos` under
`ECOM SUPERSTORE PTY LTD`, then creates and styles an isolated `Rockos`
website owned by that branch.

## Safety boundaries

- It does not create, import, rename, publish, price, or update products.
- It does not add or remove any product `website_ids`.
- It does not configure or activate payment providers or delivery carriers.
- All storefront QWeb views are scoped to the `Rockos` website after install.
- Frontend CSS and JavaScript are contained under the Rockos website layout.
- Existing companies, branches, and websites are not modified.

## Editable content

The homepage hero, category tiles, product blocks, and newsletter area contain
Odoo website-editor structures. Staff can replace images, text, links, and
dynamic-product blocks without changing the module.

Rockos contact and social values can be edited from the Rockos website record.

## Staging installation

1. Install or upgrade `rockos_website_theme` on staging.
2. Confirm the `Rockos` branch exists under `ECOM SUPERSTORE PTY LTD`.
3. Switch to the newly created `Rockos` website.
4. Review and edit homepage content.
5. Assign selected existing Odoo products to Rockos using the existing
   multi-website product field.
6. Configure Rockos-specific payments, shipping, domain, and redirects only
   after storefront review.
