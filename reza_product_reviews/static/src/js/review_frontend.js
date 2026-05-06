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

        // 2. Already reviewed message — use MutationObserver to wait for chatter
        var data = window.__rezaReviewData;
        if (!data || !data.alreadyReviewed) return;

        var target = document.getElementById('o_product_page_reviews_content') || document.body;

        var observer = new MutationObserver(function () {
            var writeForm = document.querySelector('.o_portal_chatter_composer') ||
                            document.querySelector('.o_wrating_publisher_container');

            if (!writeForm) return;
            if (document.querySelector('.reza-already-reviewed')) {
                observer.disconnect();
                return;
            }

            var msg = document.createElement('div');
            msg.className = 'alert alert-info mt-3 reza-already-reviewed';
            msg.innerHTML = '<i class="fa fa-check-circle me-2"></i> You have already submitted a review for this product. Thank you!';
            writeForm.style.display = 'none';
            writeForm.parentNode.insertBefore(msg, writeForm);
            observer.disconnect();
        });

        observer.observe(target, { childList: true, subtree: true });

        // Stop observing after 10 seconds
        setTimeout(function () { observer.disconnect(); }, 10000);
    });
})();