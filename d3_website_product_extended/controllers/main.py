# -*- coding: utf-8 -*-
from werkzeug.exceptions import NotFound

from odoo.http import request, route

from odoo.addons.website_sale.controllers.main import WebsiteSale


class D3WebsiteSale(WebsiteSale):
    """Shop grid with one card per variant, plus specification filters.

    Odoo 18 carried a full copy of the core ``shop()`` here. On Odoo 20 the
    core method exposes the hooks this needs, so only the differences remain:
    the variant cards are added in ``_get_additional_shop_values`` and the
    out-of-range page check wraps ``shop()``.
    """

    @route()
    def shop(self, page=0, **kwargs):
        response = super().shop(page=page, **kwargs)
        # website.pager() silently clamps an out-of-range page to the last one,
        # so /shop/page/200 answered 200 OK with the last page's products and a
        # canonical pointing at itself: an unbounded set of self-canonicalising
        # duplicates for crawlers. Anything past the last real page is a 404.
        pager = getattr(response, "qcontext", {}).get("pager")
        requested_page = int(page) if str(page).isdigit() else 1
        if pager and requested_page > 1 and pager["page"]["num"] != requested_page:
            raise NotFound()
        return response

    def _shop_get_query_url_kwargs(self, *args, d3_spec_filter=None, **kwargs):
        values = super()._shop_get_query_url_kwargs(*args, **kwargs)
        values["d3_spec_filter"] = d3_spec_filter
        return values

    def _get_search_options(self, *args, **kwargs):
        values = super()._get_search_options(*args, **kwargs)
        values["d3_spec_filters"] = request.httprequest.args.getlist("d3_spec_filter")
        return values

    def _get_additional_shop_values(self, values, **kwargs):
        extra_values = super()._get_additional_shop_values(values, **kwargs)
        ProductTemplate = request.env["product.template"]

        # Specification filters.
        selected_spec_filters = ProductTemplate._d3_get_selected_website_spec_filters()
        selected_spec_filter_keys = ProductTemplate._d3_get_spec_filter_keys(selected_spec_filters)
        extra_values.update({
            "d3_spec_filters": ProductTemplate._d3_get_website_spec_filter_values(
                values.get("search_product") or ProductTemplate,
                selected_spec_filter_keys,
            ),
            "d3_selected_spec_filters": selected_spec_filter_keys,
        })

        # One card per variant: each grid cell carries the variants to show.
        Product = request.env["product.product"]
        default_variants = values.get("product_variants") or {}
        all_variants = Product
        for row in values.get("bins") or []:
            for col in row:
                if not col or not col.get("product"):
                    continue
                template = col["product"]
                variants = template.get_selected_variants() or default_variants.get(template, Product)
                col["product_variants"] = variants
                all_variants |= variants

        website = request.env.website
        variant_prices = all_variants._get_sales_prices(website)
        extra_values["get_product_variants_prices"] = lambda variant: variant_prices.get(variant.id, {})
        return extra_values
