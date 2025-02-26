/** @odoo-module **/

import { WebsiteSale } from '@website_sale/js/website_sale';
import { debounce, throttleForAnimation } from "@web/core/utils/timing";

WebsiteSale.include({
    init: function () {
        this._super.apply(this, arguments);
        this._changeCreditLimitBanner = debounce(this._changeCreditLimitBanner.bind(this), 700);
    },
    _onChangeCartQuantity: async function (ev) {
        await this._super(...arguments);
        this._changeCreditLimitBanner()
    },
    _changeCreditLimitBanner: function(){
        this.rpc("/order/check_credit_limit", {}).then((data) => {
            if (data['sale_credit_limit_alert_template']){
                $("#credit_warning_section").replaceWith(data['sale_credit_limit_alert_template']);
            }
            else{
                $("#credit_warning_section").replaceWith('<div id="credit_warning_section" t-if="credit_limit_alert"></div>');
            }
        });
    }
});