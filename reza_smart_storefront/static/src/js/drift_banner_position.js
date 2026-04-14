(function () {
    'use strict';
    function ready(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }
    ready(function () {
        var banner = document.querySelector('.wyn-drift-banner-wrap');
        if (!banner) return;
        var trustBar = document.querySelector('.wp-features');
        if (!trustBar) {
            return;
        }
        trustBar.parentNode.insertAfter
        trustBar.insertAdjacentElement('afterend', banner);
    });
})();
