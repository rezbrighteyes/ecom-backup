(function () {

    // Suppress tracking for internal Odoo users
    if (document.querySelector('.o_main_navbar')) {
        return;
    }

    function trackEvent(event, params) {
        if (typeof fbq !== 'undefined') {
            params ? fbq('track', event, params) : fbq('track', event);
        }
    }

    function applyAdvancedMatching() {
        if (typeof fbq !== 'undefined' && window._fbAdvancedMatch) {
            const m = window._fbAdvancedMatch;
            if (m.em || m.ph) {
                fbq('init', '26179616351732613', {
                    em: m.em || '',
                    fn: m.fn || '',
                    ln: m.ln || '',
                    ph: m.ph ? m.ph.replace(/[^0-9]/g, '') : '',
                    ct: m.ct || '',
                    st: m.st || '',
                    zp: m.zp || '',
                    country: m.country || ''
                });
            }
        }
    }

    function bindPageEvents() {
        const path = window.location.pathname;

        applyAdvancedMatching();

        // InitiateCheckout — page load on checkout
        if (path.includes('/checkout')) {
            trackEvent('InitiateCheckout');
        }

        // Purchase — page load on confirmation
        if (path.includes('/confirmation') || path.includes('/thank')) {
            const orderTotal = document.querySelector('[data-order-amount]')?.dataset?.orderAmount
                || document.querySelector('.monetary_field')?.innerText?.replace(/[^0-9.]/g, '')
                || 0;
            const currency = document.querySelector('[data-currency]')?.dataset?.currency || 'AUD';
            trackEvent('Purchase', {
                value: parseFloat(orderTotal),
                currency: currency,
                content_type: 'product'
            });
        }

        // Search
        if (window.location.search.includes('search=')) {
            trackEvent('Search');
        }
    }

    // Event delegation — handles dynamically rendered OWL components
    function bindClickDelegation() {
        document.body.addEventListener('click', function (e) {
            const target = e.target.closest(
                '.js_add_cart, #add_to_cart, [name="add_to_cart"], ' +
                '.o_add_cart_btn, button.o_add_cart_btn, a.o_add_cart_btn'
            );
            if (target) {
                trackEvent('AddToCart');
                return;
            }

            const checkoutTarget = e.target.closest(
                'a[href*="/shop/checkout"], a[href*="/checkout"], ' +
                '.o_cart_checkout_btn, #o_payment_checkout'
            );
            if (checkoutTarget) {
                trackEvent('InitiateCheckout');
                return;
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            bindPageEvents();
            bindClickDelegation();
        });
    } else {
        bindPageEvents();
        bindClickDelegation();
    }

})();
