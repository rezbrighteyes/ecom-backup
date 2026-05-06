(function () {
    'use strict';

    function openReviewSection() {
        var reviewContent = document.getElementById('o_product_page_reviews_content');
        var reviewToggle = document.querySelector('.o_product_page_reviews_title');
        if (!reviewContent) return;

        // Remove Bootstrap collapse classes and force open
        reviewContent.classList.remove('collapse');
        reviewContent.classList.add('show');
        reviewContent.style.display = 'block';
        reviewContent.style.visibility = 'visible';
        reviewContent.style.height = 'auto';
        reviewContent.style.overflow = 'visible';

        if (reviewToggle) {
            reviewToggle.setAttribute('aria-expanded', 'true');
            reviewToggle.classList.remove('collapsed');
        }

        // Kill Bootstrap collapse instance if it exists
        if (window.bootstrap && window.bootstrap.Collapse) {
            try {
                var instance = window.bootstrap.Collapse.getInstance(reviewContent);
                if (instance) instance.dispose();
                // Recreate as shown
                new window.bootstrap.Collapse(reviewContent, { toggle: false });
            } catch(e) {}
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

    document.addEventListener('DOMContentLoaded', function () {
        openReviewSection();
        setTimeout(openReviewSection, 200);
        setTimeout(openReviewSection, 600);
        setTimeout(openReviewSection, 1500);
    });

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