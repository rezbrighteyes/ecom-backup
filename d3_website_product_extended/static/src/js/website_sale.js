/** @odoo-module **/
import { WebsiteSale } from "@website_sale/js/website_sale";
import { renderToString } from "@web/core/utils/render";

WebsiteSale.include({
     start: async function(){
        const def = await this._super(...arguments);
        let parentDiv = document.querySelector(".variant-div");
        if (parentDiv){
            let items = parentDiv.children;
            let hiddenCount = items.length - 4;

            for (let i = 4; i < items.length; i++) {
                items[i].classList.add("hide-variant");
            }
            if (hiddenCount > 0) {
                var $button = $('<div>', {
                html: `<b>${hiddenCount}+</b>`,
                class: 'form-check mb-1 variant-radio variant-button text-secondary',
                click: function() {
                    let hiddenItems = document.querySelectorAll(".hide-variant");
                    hiddenItems.forEach(item => item.classList.remove("hide-variant"));
                    $button.css("display", "none");
                }
                });

                parentDiv.insertBefore($button[0], items[4]);
            }

        }
        return def;
     },
     _onChangeCombination: function (ev, $parent, combination) {
		this._super.apply(this, arguments);
		var product_variant_input = $parent.find(".variant-div").find("input.js_product_change:checked");
		var product_attribute_variants_data = product_variant_input.data('variant-attributes')
        var product_attribute_variants = new Array()
        if (product_attribute_variants_data){
            product_attribute_variants = JSON.parse(product_attribute_variants_data.replace(/'/g, '"'))
        }
        const xml = renderToString("d3_website_product_extended.ProductVariantAttributes", {
            variant_attributes: product_attribute_variants,
        });
        const div = new DOMParser().parseFromString(xml, "text/html").querySelector("div");
        div.classList.add("variant-content");

        const variantContent = document.querySelector(".variant-content");
        if (variantContent) {
            variantContent.remove();
        }
        const variantDiv = document.querySelector(".variant-div");
        if (variantDiv){
            variantDiv.parentNode.insertBefore(div, variantDiv);
        }
	},
});
