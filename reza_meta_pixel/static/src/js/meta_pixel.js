(function () {

    function trackEvent(event, params) {
        if (typeof fbq !== 'undefined') {
            params ? fbq('track', event, params) : fbq('track', event);
        }
    }

    function bindEvents() {
        const path = window.location.pathname;

        // InitiateCheckout — page load on checkout
        if (path.includes('/checkout')) {
            trackEvent('InitiateCheckout');
        }

        // InitiateCheckout — clicking checkout button from cart
        document.querySelectorAll(
            'a[href*="/shop/checkout"], a[href*="/checkout"], .o_cart_checkout_btn, #o_payment_checkout'
        ).forEach(btn => {
            btn.addEventListener('click', () => {
                trackEvent('InitiateCheckout');
            });
        });

        // AddToCart — button click
        document.querySelectorAll(
            'a.o_add_cart_btn, button.o_add_cart_btn, .js_add_cart, #add_to_cart, [name="add_to_cart"]'
        ).forEach(btn => {
            btn.addEventListener('click', () => {
                trackEvent('AddToCart');
            });
        });

        // Purchase — fires on confirmation page
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

    // Run immediately if DOM is ready, otherwise wait
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindEvents);
    } else {
        bindEvents();
    }

})();
