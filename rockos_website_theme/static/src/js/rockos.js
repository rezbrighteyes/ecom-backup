/** @odoo-module **/

document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector(".rockos-site .rockos-menu-toggle");
    const menu = document.querySelector(".rockos-site .rockos-mobile-nav");
    if (toggle && menu) {
        toggle.addEventListener("click", () => menu.classList.toggle("is-open"));
    }
});
