(function () {
    'use strict';

    // ── Stat counter animation ─────────────────────────────
    function animateCounter(el, target, duration) {
        var start = 0;
        var step = target / (duration / 16);
        var timer = setInterval(function () {
            start += step;
            if (start >= target) {
                start = target;
                clearInterval(timer);
            }
            el.textContent = Math.floor(start);
        }, 16);
    }

    // ── Intersection Observer for scroll animations ────────
    function initScrollAnimations() {
        // Fade in sections
        var fadeEls = document.querySelectorAll(
            '.dk-feature, .dk-edition, .dk-trust-item'
        );
        fadeEls.forEach(function (el, i) {
            el.style.opacity = '0';
            el.style.transform = 'translateY(24px)';
            el.style.transition = 'opacity 0.5s ease ' + (i % 3 * 0.1) + 's, transform 0.5s ease ' + (i % 3 * 0.1) + 's';
        });

        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.15 });

        fadeEls.forEach(function (el) { observer.observe(el); });

        // Stat counters
        var statEls = document.querySelectorAll('.dk-stat-val');
        var targets = [30, 10, 40];
        var statObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry, i) {
                if (entry.isIntersecting) {
                    var target = parseInt(entry.target.getAttribute('data-target'));
                    animateCounter(entry.target, target, 1200);
                    statObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        statEls.forEach(function (el, i) {
            el.setAttribute('data-target', targets[i] || el.textContent);
            el.textContent = '0';
            statObserver.observe(el);
        });
    }

    // ── Init ───────────────────────────────────────────────
    if (document.querySelector('.dk-page')) {
        if (document.readyState !== 'loading') {
            initScrollAnimations();
        } else {
            document.addEventListener('DOMContentLoaded', initScrollAnimations);
        }
    }
})();
