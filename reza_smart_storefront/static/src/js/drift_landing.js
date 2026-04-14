(function () {
    'use strict';

    if (!document.querySelector('.dk-page')) return;

    // ── 1. SPEED LAUNCH INTRO ──────────────────────────────
    function initLaunchIntro() {
        var content = document.querySelector('.dk-hero-text');
        var model = document.querySelector('.dk-hero-model');
        if (!content) return;

        content.style.cssText += 'opacity:0;transform:translateX(-120px);transition:none;';
        if (model) model.style.cssText += 'opacity:0;transform:translateX(120px);transition:none;';

        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                content.style.transition = 'opacity 0.6s cubic-bezier(0.16,1,0.3,1), transform 0.6s cubic-bezier(0.16,1,0.3,1)';
                content.style.opacity = '1';
                content.style.transform = 'translateX(0)';

                if (model) {
                    model.style.transition = 'opacity 0.6s cubic-bezier(0.16,1,0.3,1) 0.15s, transform 0.6s cubic-bezier(0.16,1,0.3,1) 0.15s';
                    model.style.opacity = '1';
                    model.style.transform = 'translateX(0)';
                }
            });
        });
    }

    // ── 2. LIVE DRIFT SPEEDOMETER ──────────────────────────
    function initSpeedometer() {
        var container = document.querySelector('.dk-speedometer-wrap');
        if (!container) return;

        var canvas = document.createElement('canvas');
        canvas.width = 220;
        canvas.height = 220;
        canvas.style.cssText = 'display:block;margin:0 auto;';
        container.appendChild(canvas);

        var ctx = canvas.getContext('2d');
        var maxSpeed = 30;
        var currentSpeed = 0;
        var targetSpeed = 0;
        var animating = false;

        function degToRad(deg) { return deg * Math.PI / 180; }

        function drawSpeedometer(speed) {
            var cx = 110, cy = 120, r = 90;
            ctx.clearRect(0, 0, 220, 220);

            // Background arc
            ctx.beginPath();
            ctx.arc(cx, cy, r, degToRad(150), degToRad(390));
            ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            ctx.lineWidth = 12;
            ctx.lineCap = 'round';
            ctx.stroke();

            // Speed arc
            var pct = speed / maxSpeed;
            var endAngle = 150 + (pct * 240);
            var gradient = ctx.createLinearGradient(cx - r, cy, cx + r, cy);
            gradient.addColorStop(0, '#D4AF37');
            gradient.addColorStop(1, '#ff6b35');
            ctx.beginPath();
            ctx.arc(cx, cy, r, degToRad(150), degToRad(endAngle));
            ctx.strokeStyle = gradient;
            ctx.lineWidth = 12;
            ctx.lineCap = 'round';
            ctx.stroke();

            // Tick marks
            for (var i = 0; i <= 6; i++) {
                var angle = degToRad(150 + i * 40);
                var x1 = cx + (r - 18) * Math.cos(angle);
                var y1 = cy + (r - 18) * Math.sin(angle);
                var x2 = cx + (r - 6) * Math.cos(angle);
                var y2 = cy + (r - 6) * Math.sin(angle);
                ctx.beginPath();
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.strokeStyle = 'rgba(255,255,255,0.4)';
                ctx.lineWidth = 2;
                ctx.stroke();
            }

            // Needle
            var needleAngle = degToRad(150 + (speed / maxSpeed) * 240);
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(
                cx + (r - 25) * Math.cos(needleAngle),
                cy + (r - 25) * Math.sin(needleAngle)
            );
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.stroke();

            // Centre dot
            ctx.beginPath();
            ctx.arc(cx, cy, 6, 0, Math.PI * 2);
            ctx.fillStyle = '#D4AF37';
            ctx.fill();

            // Speed text
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 36px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(Math.floor(speed), cx, cy + 48);

            ctx.fillStyle = '#D4AF37';
            ctx.font = 'bold 12px sans-serif';
            ctx.fillText('KM/H', cx, cy + 66);
        }

        function animateTo(target) {
            targetSpeed = target;
            if (animating) return;
            animating = true;
            function step() {
                var diff = targetSpeed - currentSpeed;
                if (Math.abs(diff) < 0.3) {
                    currentSpeed = targetSpeed;
                    drawSpeedometer(currentSpeed);
                    animating = false;
                    return;
                }
                currentSpeed += diff * 0.06;
                drawSpeedometer(currentSpeed);
                requestAnimationFrame(step);
            }
            requestAnimationFrame(step);
        }

        drawSpeedometer(0);

        // Rev up on load
        setTimeout(function () { animateTo(28); }, 600);
        setTimeout(function () { animateTo(30); }, 1800);

        // Rev on hover
        var hero = document.querySelector('.dk-hero');
        if (hero) {
            hero.addEventListener('mouseenter', function () { animateTo(30); });
            hero.addEventListener('mouseleave', function () { animateTo(18); });
        }
    }

    // ── 3. EDITION COLOUR TAKEOVER ─────────────────────────
    var editionThemes = {
        'Shadow Storm':  { bg: '#0a0a0a', accent: '#888', text: '#fff', card: '#1a1a1a' },
        'Pink Crystal':  { bg: '#1a0510', accent: '#e91e8c', text: '#fff', card: '#2a0a1a' },
        'Inferno Line':  { bg: '#1a0800', accent: '#ff4500', text: '#fff', card: '#2a0f00' },
        'Ice & Fire':    { bg: '#000d1a', accent: '#0088ff', text: '#fff', card: '#001a2a' },
        'Urban Rebel':   { bg: '#0d0d0d', accent: '#ff2020', text: '#fff', card: '#1a0505' },
    };

    var defaultTheme = {
        featBg: '#f7f7f7', edBg: '#fff', trustBg: '#f7f7f7',
        featCard: '#fff', featBorder: 'rgba(0,0,0,0.07)',
        featTitle: '#0a0a0a', featText: 'rgba(10,10,10,0.55)',
        edTitle: '#0a0a0a', edBorder: 'rgba(0,0,0,0.08)',
        trustText: '#0a0a0a', trustSub: 'rgba(10,10,10,0.5)',
        sectionTitle: '#0a0a0a', sectionSub: 'rgba(10,10,10,0.5)',
    };

    function applyEditionTheme(theme) {
        var featSection = document.querySelector('.dk-features-section');
        var edSection = document.querySelector('.dk-editions-section');
        var trustSection = document.querySelector('.dk-trust-section');
        var sectionTitles = document.querySelectorAll('.dk-features-section .dk-section-title, .dk-editions-section .dk-section-title');
        var sectionSubs = document.querySelectorAll('.dk-section-sub');
        var features = document.querySelectorAll('.dk-feature');
        var trustItems = document.querySelectorAll('.dk-trust-item strong, .dk-trust-item span');

        var transition = 'background 0.4s ease, border-color 0.4s ease, color 0.4s ease';

        if (featSection) {
            featSection.style.transition = 'background 0.4s ease';
            featSection.style.background = theme.bg;
        }
        if (edSection) {
            edSection.style.transition = 'background 0.4s ease';
            edSection.style.background = theme.bg;
        }
        if (trustSection) {
            trustSection.style.transition = 'background 0.4s ease';
            trustSection.style.background = theme.bg;
        }

        sectionTitles.forEach(function (el) {
            el.style.transition = 'color 0.4s ease';
            el.style.color = theme.text;
        });

        sectionSubs.forEach(function (el) {
            el.style.transition = 'color 0.4s ease';
            el.style.color = 'rgba(255,255,255,0.55)';
        });

        features.forEach(function (el) {
            el.style.transition = transition;
            el.style.background = theme.card;
            el.style.borderColor = theme.accent + '44';
            el.querySelector('h3').style.color = theme.text;
            el.querySelector('p').style.color = 'rgba(255,255,255,0.55)';
        });

        trustItems.forEach(function (el) {
            el.style.transition = 'color 0.4s ease';
            el.style.color = theme.text;
        });
    }

    function resetTheme() {
        var featSection = document.querySelector('.dk-features-section');
        var edSection = document.querySelector('.dk-editions-section');
        var trustSection = document.querySelector('.dk-trust-section');
        var sectionTitles = document.querySelectorAll('.dk-features-section .dk-section-title, .dk-editions-section .dk-section-title');
        var sectionSubs = document.querySelectorAll('.dk-section-sub');
        var features = document.querySelectorAll('.dk-feature');
        var trustItems = document.querySelectorAll('.dk-trust-item strong, .dk-trust-item span');

        if (featSection) featSection.style.background = '#f7f7f7';
        if (edSection) edSection.style.background = '#fff';
        if (trustSection) trustSection.style.background = '#f7f7f7';

        sectionTitles.forEach(function (el) { el.style.color = '#0a0a0a'; });
        sectionSubs.forEach(function (el) { el.style.color = 'rgba(10,10,10,0.5)'; });

        features.forEach(function (el) {
            el.style.background = '#fff';
            el.style.borderColor = 'rgba(0,0,0,0.07)';
            el.querySelector('h3').style.color = '#0a0a0a';
            el.querySelector('p').style.color = 'rgba(10,10,10,0.55)';
        });

        trustItems.forEach(function (el) { el.style.color = ''; });
    }

    function initColourTakeover() {
        var editions = document.querySelectorAll('.dk-edition');
        editions.forEach(function (el) {
            var name = el.querySelector('.dk-edition-name').textContent.trim();
            var theme = editionThemes[name];
            if (!theme) return;

            el.addEventListener('mouseenter', function () {
                applyEditionTheme(theme);
                // Highlight this edition
                el.style.borderColor = theme.accent;
                el.style.boxShadow = '0 8px 40px ' + theme.accent + '44';
            });

            el.addEventListener('mouseleave', function () {
                resetTheme();
                el.style.borderColor = '';
                el.style.boxShadow = '';
            });
        });
    }

    // ── Scroll fade-ins ────────────────────────────────────
    function initScrollAnimations() {
        var fadeEls = document.querySelectorAll('.dk-feature, .dk-edition, .dk-trust-item');
        fadeEls.forEach(function (el, i) {
            el.style.opacity = '0';
            el.style.transform = 'translateY(24px)';
            el.style.transition = 'opacity 0.5s ease ' + (i % 3 * 0.08) + 's, transform 0.5s ease ' + (i % 3 * 0.08) + 's';
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
    }

    // ── Boot ───────────────────────────────────────────────
    function boot() {
        initLaunchIntro();
        initSpeedometer();
        initColourTakeover();
        initScrollAnimations();
    }

    if (document.readyState !== 'loading') { boot(); }
    else { document.addEventListener('DOMContentLoaded', boot); }

})();
