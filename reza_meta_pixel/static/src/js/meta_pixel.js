(function () {

    // Suppress tracking for internal Odoo users (admins/staff)
    if (document.querySelector('.o_main_navbar')) {
        return;
    }

    function trackEvent(event, params) {
        if (typeof fbq !== 'undefined') {
            params ? fbq('track', event, params) : fbq('track', event);
        }
    }

    // Advanced Matching — update fbq init with real customer data if available
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

    function bindEvents() {
        const path = window.location.pathname;

        applyAdvancedMatching();

        // InitiateCheckout — page load
        if (path.includes('/checkout')) {
            trackEvent('InitiateCheckout');
        }

        // InitiateCheckout — checkout button click from cart
        document.querySelectorAll(
            'a[href*="/shop/checkout"], a[href*="/checkout"], .o_cart_checkout_btn, #o_payment_checkout'
        ).forEach(btn => {
            btn.addEventListener('click', () => {
                trackEvent('InitiateCheckout');
            });
        });

        // AddToCart
        document.querySelectorAll(
            'a.o_add_cart_btn, button.o_add_cart_btn, .js_add_cart, #add_to_cart, [name="add_to_cart"]'
        ).forEach(btn => {
            btn.addEventListener('click', () => {
                trackEvent('AddToCart');
            });
        });

        // Purchase
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

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindEvents);
    } else {
        bindEvents();
    }

})();
