(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    ready(function () {
        // 1. Open review section by default
        var reviewContent = document.getElementById('o_product_page_reviews_content');
        var reviewToggle = document.querySelector('.o_product_page_reviews_title');
        if (reviewContent) {
            reviewContent.classList.add('show');
            if (reviewToggle) {
                reviewToggle.setAttribute('aria-expanded', 'true');
                reviewToggle.classList.remove('collapsed');
            }
        }

        // 2. Already reviewed message — check Shadow DOM
        var data = window.__rezaReviewData;
        if (!data || !data.alreadyReviewed) return;

        var chatterRoot = document.getElementById('chatterRoot');
        if (!chatterRoot) return;

        function hideComposerAndShowMessage() {
            var shadowRoot = chatterRoot.shadowRoot;
            if (!shadowRoot) return false;

            var composer = shadowRoot.querySelector('.o-mail-Composer');
            if (!composer) return false;

            if (shadowRoot.querySelector('.reza-already-reviewed')) return true;

            var msg = document.createElement('div');
            msg.className = 'alert alert-info mt-3 reza-already-reviewed';
            msg.style.cssText = 'padding:12px 16px; border-radius:8px; background:#d1ecf1; border:1px solid #bee5eb; color:#0c5460; margin:12px 0;';
            msg.innerHTML = '<i class="fa fa-check-circle" style="margin-right:8px;"></i> You have already submitted a review for this product. Thank you!';

            composer.style.display = 'none';
            composer.parentNode.insertBefore(msg, composer);
            return true;
        }

        // Try immediately
        if (hideComposerAndShowMessage()) return;

        // Otherwise observe shadow root changes
        var observer = new MutationObserver(function () {
            if (hideComposerAndShowMessage()) {
                observer.disconnect();
            }
        });

        // Observe chatterRoot for shadow DOM attachment
        observer.observe(chatterRoot, { childList: true, subtree: true });

        // Also try polling since MutationObserver doesn't observe shadow DOM changes
        var poll = setInterval(function () {
            if (hideComposerAndShowMessage()) {
                clearInterval(poll);
                observer.disconnect();
            }
        }, 300);

        setTimeout(function () {
            clearInterval(poll);
            observer.disconnect();
        }, 10000);
    });
})();