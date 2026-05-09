(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') { fn(); }
        else { document.addEventListener('DOMContentLoaded', fn); }
    }

    ready(function () {

        /* ── 1. Counter animation ── */
        var counterEl = document.querySelector('[data-counter]');
        if (counterEl) {
            var target = parseInt(counterEl.getAttribute('data-counter'));
            var fired = false;
            new IntersectionObserver(function (entries) {
                if (entries[0].isIntersecting && !fired) {
                    fired = true;
                    var start = performance.now();
                    (function tick(now) {
                        var p = Math.min((now - start) / 2000, 1);
                        var ease = 1 - Math.pow(1 - p, 4);
                        counterEl.textContent = Math.floor(target * ease).toLocaleString();
                        if (p < 1) { requestAnimationFrame(tick); }
                        else { counterEl.textContent = target.toLocaleString(); }
                    })(start);
                }
            }, { threshold: 0.5 }).observe(counterEl.closest('.wp-feature'));
        }

        /* ── 2. Marquee (mobile only) ── */
        if (window.innerWidth > 520) { return; }

        var grid = document.querySelector('.wp-features__grid');
        if (!grid) { return; }

        var track = document.createElement('div');
        track.className = 'wp-features__track';
        Array.from(grid.children).forEach(function (c) { track.appendChild(c); });

        var clone = track.cloneNode(true);
        clone.setAttribute('aria-hidden', 'true');

        grid.appendChild(track);
        grid.appendChild(clone);

        function pause() {
            track.classList.add('paused');
            clone.classList.add('paused');
        }
        function resume() {
            track.classList.remove('paused');
            clone.classList.remove('paused');
        }

        grid.addEventListener('touchstart', pause, { passive: true });
        grid.addEventListener('touchend', function () {
            setTimeout(resume, 900);
        }, { passive: true });

    });

})();