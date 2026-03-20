document.addEventListener('DOMContentLoaded', function() {
    function makeToast() {
        var t = document.createElement('div');
        t.id = 'sf-cart-toast';
        t.style.cssText = 'position:fixed;top:20px;right:20px;background:#fff;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,0.15);padding:16px 20px;z-index:9999;display:none;min-width:280px;border:1px solid rgba(0,0,0,0.08);';

        var header = document.createElement('div');
        header.style.cssText = 'display:flex;align-items:center;gap:12px;margin-bottom:12px;';
        var dot = document.createElement('div');
        dot.style.cssText = 'width:8px;height:8px;border-radius:50%;background:#10b981;flex-shrink:0;';
        var title = document.createElement('strong');
        title.style.fontSize = '14px';
        title.textContent = 'Added to cart';
        var close = document.createElement('span');
        close.style.cssText = 'margin-left:auto;cursor:pointer;color:#999;font-size:18px;';
        close.textContent = '\u00d7';
        close.addEventListener('click', function() { t.style.display = 'none'; });
        header.appendChild(dot);
        header.appendChild(title);
        header.appendChild(close);

        var product = document.createElement('div');
        product.id = 'sf-toast-product';
        product.style.cssText = 'display:flex;align-items:center;gap:10px;';

        var link = document.createElement('a');
        link.href = '/shop/cart';
        link.style.cssText = 'display:block;text-align:center;background:#0F1720;color:#fff;padding:10px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;margin-top:12px;';
        link.textContent = 'View cart';

        t.appendChild(header);
        t.appendChild(product);
        t.appendChild(link);
        document.body.appendChild(t);
        return t;
    }

    var forms = document.querySelectorAll('.sf-sidebar form');
    if (!forms.length) return;

    var toast = makeToast();

    forms.forEach(function(form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            var btn = form.querySelector('.sf-add-cart');
            var item = form.closest('.sf-related-item');
            var name = item ? item.querySelector('.sf-related-name').textContent : '';
            var price = item ? item.querySelector('.sf-related-price').textContent : '';
            var productId = form.querySelector('input[name="product_id"]').value;

            btn.style.opacity = '0.5';

            fetch('/shop/cart/update_json', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {product_id: parseInt(productId), add_qty: 1}
                }),
                credentials: 'same-origin'
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
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

                    var tp = document.getElementById('sf-toast-product');
                    tp.textContent = '';

                    var tImg = document.createElement('img');
                    tImg.src = '/web/image/product.product/' + productId + '/image_128';
                    tImg.style.cssText = 'width:48px;height:48px;border-radius:8px;object-fit:cover;';

                    var tInfo = document.createElement('div');
                    var tName = document.createElement('div');
                    tName.style.cssText = 'font-size:13px;font-weight:600;';
                    tName.textContent = name;
                    var tPrice = document.createElement('div');
                    tPrice.style.cssText = 'font-size:14px;color:#D4AF37;font-weight:700;';
                    tPrice.textContent = price;
                    tInfo.appendChild(tName);
                    tInfo.appendChild(tPrice);
                    tp.appendChild(tImg);
                    tp.appendChild(tInfo);

                    toast.style.display = 'block';
                    setTimeout(function() { toast.style.display = 'none'; }, 4000);
                    setTimeout(function() {
                        btn.style.background = '';
                        btn.style.borderColor = '';
                        btn.style.color = '';
                    }, 2000);
                }
            })
            .catch(function() {
                btn.style.opacity = '1';
                form.submit();
            });
        });
    });
});
