document.addEventListener('DOMContentLoaded', () => {

    const path = window.location.pathname;

    // Purchase — fires on confirmation page, reads order total from DOM
    if (path.includes('/shop/confirmation')) {
        const orderTotal = document.querySelector('[data-order-amount]')?.dataset?.orderAmount
            || document.querySelector('.monetary_field')?.innerText?.replace(/[^0-9.]/g, '')
            || 0;
        const currency = document.querySelector('[data-currency]')?.dataset?.currency || 'AUD';
        fbq('track', 'Purchase', {
            value: parseFloat(orderTotal),
            currency: currency,
            content_type: 'product'
        });
    }

    // InitiateCheckout
    if (path.includes('/shop/checkout')) {
        fbq('track', 'InitiateCheckout');
    }

    // AddToCart — button click
    document.querySelectorAll(
        'a.o_add_cart_btn, button.o_add_cart_btn, .js_add_cart, #add_to_cart'
    ).forEach(btn => {
        btn.addEventListener('click', () => {
            fbq('track', 'AddToCart');
        });
    });

    // Search
    if (window.location.search.includes('search=')) {
        fbq('track', 'Search');
    }

});
