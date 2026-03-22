(function () {
    "use strict";

    function ready(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    ready(function () {
        var sidebar = document.getElementById('sf_sidebar');
        if (!sidebar) return;

        var buttons = sidebar.querySelectorAll('.sf-add-cart');
        if (!buttons.length) return;

        // Build toast
        var toast = document.createElement('div');
        toast.style.cssText = 'position:fixed;top:20px;right:20px;background:#fff;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,0.15);padding:16px 20px;z-index:9999;display:none;min-width:280px;max-width:340px;border:1px solid rgba(0,0,0,0.08);';

        var toastHeader = document.createElement('div');
        toastHeader.style.cssText = 'display:flex;align-items:center;gap:12px;margin-bottom:12px;';

        var dot = document.createElement('div');
        dot.style.cssText = 'width:8px;height:8px;border-radius:50%;background:#10b981;flex-shrink:0;';
        toastHeader.appendChild(dot);

        var toastTitle = document.createElement('strong');
        toastTitle.style.fontSize = '14px';
        toastTitle.textContent = 'Added to cart';
        toastHeader.appendChild(toastTitle);

        var toastClose = document.createElement('span');
        toastClose.style.cssText = 'margin-left:auto;cursor:pointer;color:#999;font-size:18px;line-height:1;';
        toastClose.textContent = '\u00d7';
        toastClose.addEventListener('click', function () { toast.style.display = 'none'; });
        toastHeader.appendChild(toastClose);

        var toastBody = document.createElement('div');
        toastBody.style.cssText = 'display:flex;align-items:center;gap:10px;';

        var toastImg = document.createElement('img');
        toastImg.style.cssText = 'width:48px;height:48px;border-radius:8px;object-fit:cover;';

        var toastInfo = document.createElement('div');
        var toastName = document.createElement('div');
        toastName.style.cssText = 'font-size:13px;font-weight:600;';
        var toastPrice = document.createElement('div');
        toastPrice.style.cssText = 'font-size:14px;color:#D4AF37;font-weight:700;';
        toastInfo.appendChild(toastName);
        toastInfo.appendChild(toastPrice);
        toastBody.appendChild(toastImg);
        toastBody.appendChild(toastInfo);

        var toastLink = document.createElement('a');
        toastLink.href = '/shop/cart';
        toastLink.style.cssText = 'display:block;text-align:center;background:#0F1720;color:#fff;padding:10px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;margin-top:12px;';
        toastLink.textContent = 'View cart';

        toast.appendChild(toastHeader);
        toast.appendChild(toastBody);
        toast.appendChild(toastLink);
        document.body.appendChild(toast);

        var hideTimer = null;

        function showToast(variantId, name, price) {
            toastImg.src = '/web/image/product.product/' + variantId + '/image_128';
            toastName.textContent = name;
            toastPrice.textContent = price;
            toast.style.display = 'block';
            if (hideTimer) clearTimeout(hideTimer);
            hideTimer = setTimeout(function () { toast.style.display = 'none'; }, 4000);
        }

        function getCsrf() {
            var el = document.querySelector('input[name="csrf_token"]');
            return el ? el.value : '';
        }

        buttons.forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();

                var item = btn.closest('.sf-related-item');
                var variantId = btn.getAttribute('data-variant-id');
                var name = item.getAttribute('data-name');
                var price = item.getAttribute('data-price');

                btn.style.opacity = '0.5';

                var xhr = new XMLHttpRequest();
                xhr.open('POST', '/shop/cart/update_json', true);
                xhr.setRequestHeader('Content-Type', 'application/json');
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
                xhr.onload = function () {
                    if (xhr.status === 200) {
                        try {
                            var data = JSON.parse(xhr.responseText);
                            if (data.result) {
                                btn.style.opacity = '1';
                                btn.style.background = '#10b981';
                                btn.style.borderColor = '#10b981';
                                btn.style.color = '#fff';

                                var badge = document.querySelector('.my_cart_quantity');
                                if (badge) {
                                    badge.textContent = data.result.cart_quantity;
                                    badge.classList.remove('d-none');
                                }

                                showToast(variantId, name, price);

                                setTimeout(function () {
                                    btn.style.background = '';
                                    btn.style.borderColor = '';
                                    btn.style.color = '';
                                }, 2000);
                                return;
                            }
                        } catch (err) {}
                    }
                    // Fallback
                    window.location.href = '/shop/cart/update?product_id=' + variantId + '&add_qty=1&csrf_token=' + getCsrf();
                };
                xhr.onerror = function () {
                    window.location.href = '/shop/cart/update?product_id=' + variantId + '&add_qty=1&csrf_token=' + getCsrf();
                };
                xhr.send(JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {product_id: parseInt(variantId), add_qty: 1}
                }));
            });
        });
    });
})();
