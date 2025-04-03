/** @odoo-module **/
import { WebsiteSale } from "@website_sale/js/website_sale";

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
});
