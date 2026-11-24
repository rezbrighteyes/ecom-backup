(function () {
    'use strict';

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
        msg.innerHTML = '<i class="oi oi-filled" data-icon="check_circle" style="margin-right:8px;"></i> You have already submitted a review for this product. Thank you!';
        composer.style.display = 'none';
        composer.parentNode.insertBefore(msg, composer);
    }

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