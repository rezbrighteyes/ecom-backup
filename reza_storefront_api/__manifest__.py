# -*- coding: utf-8 -*-
{
    "name": "Reza Storefront API",
    "summary": "Read-only, token-protected catalogue export for the static storefront build",
    "description": """
Catalogue export contract v1 (docs/STOREFRONT_CATALOGUE_CONTRACT.md).

GET /storefront/v1/catalogue/meta and GET /storefront/v1/catalogue?page=&limit=
answer the same minimal JSON 404 as any unknown path unless: the
X-Storefront-Token header matches the ir.config_parameter
reza_storefront_api.token (32+ characters; empty, short or missing closes the
endpoint), the request carries no session cookie, the Host is exactly one
website's own domain, and that shop is open to anonymous visitors.

Records are selected as the website's public user (record rules apply);
sudo() only reads the contract fields of what was selected. Prices use the
public partner's pricelist and fiscal position with no session, cart or GeoIP.

The module adds no model of its own and no public method. Every read is in
plain module functions (catalogue.py) that only the controller calls. The
only ORM extension is a private ir.http._pre_dispatch hook that turns
framework pre-dispatch failures on this route into the same 404.
data/neutralize.sql deletes the token on an Odoo.sh staging restore.
""",
    "version": "20.0.1.1.0",
    "category": "Website/eCommerce",
    "author": "Reza D Shiraz",
    "license": "OPL-1",
    # website_sale_stock: the stock figure and band come from
    #   website._get_product_available_qty, which website_sale_stock binds to
    #   the website's warehouse (reza_ecom_edbert_stock overrides the same
    #   method when installed; it is deliberately NOT a dependency, so this
    #   module installs without the Edbert bridge).
    # sh_product_multi_website: its sale_product_domain() override is the
    #   website_ids rule that decides which website a product is on.
    # RezaDs_seo_auto: per-website meta title / description / body overrides
    #   (product.website.seo) through _seo_for_website / _seo_body_override.
    # product_data_feed_brand: product.template.feed_brand_id is the brand
    #   field this database uses (2988 of 2988 published products carry one;
    #   the "brand" product attribute has 0 lines).
    "depends": [
        "website_sale_stock",
        "sh_product_multi_website",
        "RezaDs_seo_auto",
        "product_data_feed_brand",
    ],
    "data": [],
    "installable": True,
    "application": False,
}
