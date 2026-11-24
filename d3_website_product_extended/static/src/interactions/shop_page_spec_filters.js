import { patch } from "@web/core/utils/patch";
import { ShopPage } from "@website_sale/interactions/shop_page";

/**
 * Odoo 20 rebuilds the shop query from scratch on every filter change and
 * keeps only `attribute_value` and `tags`, then posts it to /shop/reload as a
 * JSON object (duplicate keys collapse). Carry the ticked specification
 * filters as ONE comma-joined `d3_spec_filter` parameter, like core does for
 * tags; the server splits it again.
 */
patch(ShopPage.prototype, {
    _getSearchParams(form) {
        const searchParams = super._getSearchParams(form);
        const specs = [...form.querySelectorAll('input[name="d3_spec_filter"]:checked')]
            .map((input) => input.value)
            .filter(Boolean);
        searchParams.delete("d3_spec_filter");
        if (specs.length) {
            searchParams.set("d3_spec_filter", [...new Set(specs)].join(","));
        }
        return searchParams;
    },
});
