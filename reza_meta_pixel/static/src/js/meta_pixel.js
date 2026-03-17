document.addEventListener('DOMContentLoaded', () => {
    // AddToCart
    document.querySelectorAll('a.o_add_cart_btn, button.o_add_cart_btn, .js_add_cart').forEach(btn => {
        btn.addEventListener('click', () => {
            fbq('track', 'AddToCart');
        });
    });

    // InitiateCheckout
    const checkoutBtn = document.querySelector('a[href="/shop/checkout"], .o_payment_checkout');
    if (checkoutBtn) {
        checkoutBtn.addEventListener('click', () => {
            fbq('track', 'InitiateCheckout');
        });
    }
});
