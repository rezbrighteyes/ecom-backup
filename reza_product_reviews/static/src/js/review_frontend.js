(function () {
    'use strict';

    function forceOpenReviews() {
        var toggle = document.querySelector('.o_product_page_reviews_title');
        if (toggle) {
            toggle.removeAttribute('data-bs-toggle');
            toggle.removeAttribute('data-bs-target');
        }
        var el = document.getElementById('o_product_page_reviews_content');
        if (!el) return;
        el.classList.add('show');
        el.style.display = 'block';
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'true');
            toggle.classList.remove('collapsed');
        }
    }

    function hideComposerIfReviewed() {
        var data = window.__rezaReviewData;
        if (!data || !data.alreadyReviewed) return;

        var chatterRoot = document.getElementById('chatterRoot');
        if (!chatterRoot || !chatterRoot.shadowRoot) return;

        var composer = chatterRoot.shadowRoot.querySelector('.o-mail-Composer');
        if (!composer) return;

        if (chatterRoot.shadowRoot.querySelector('.reza-already-reviewed')) return;

        var msg = document.createElement('div');
        msg.className = 'reza-already-reviewed';
        msg.style.cssText = 'padding:12px 16px; border-radius:8px; background:#d1ecf1; border:1px solid #bee5eb; color:#0c5460; margin:12px 0;';
        msg.innerHTML = '<i class="fa fa-check-circle" style="margin-right:8px;"></i> You have already submitted a review for this product. Thank you!';
        composer.style.display = 'none';
        composer.parentNode.insertBefore(msg, composer);
    }

    // Open on DOM ready and again after Bootstrap hydration
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', forceOpenReviews);
    } else {
        forceOpenReviews();
    }
    setTimeout(forceOpenReviews, 1500);

    // Poll for shadow DOM
    setTimeout(function () {
        var attempts = 0;
        var poll = setInterval(function () {
            attempts++;
            hideComposerIfReviewed();
            if (attempts > 75) clearInterval(poll);
        }, 200);
    }, 500);

})();