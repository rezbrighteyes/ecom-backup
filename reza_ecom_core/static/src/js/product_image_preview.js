/** @odoo-module **/

const OVERLAY_ID = "reza_product_image_preview_overlay";
const STYLE_ID = "reza_product_image_preview_style";

function fullSizeImageUrl(src) {
    const url = new URL(src, window.location.origin);
    url.pathname = url.pathname.replace(/\/image_[^/]+$/, "/image_1920");
    return `${url.pathname}${url.search}`;
}

function ensureStyle() {
    if (document.getElementById(STYLE_ID)) {
        return;
    }
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = `
        .o_form_readonly [name="image_1920"].o_field_widget img {
            cursor: zoom-in;
        }
    `;
    document.head.appendChild(style);
}

function closeOverlay() {
    const overlay = document.getElementById(OVERLAY_ID);
    if (overlay) {
        overlay.remove();
    }
}

function showOverlay(src, alt) {
    closeOverlay();

    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.style.cssText = [
        "position:fixed",
        "inset:0",
        "z-index:20000",
        "background:rgba(0,0,0,.78)",
        "display:flex",
        "align-items:center",
        "justify-content:center",
        "padding:32px",
    ].join(";");

    const panel = document.createElement("div");
    panel.style.cssText = [
        "position:relative",
        "max-width:min(1100px,96vw)",
        "max-height:92vh",
        "background:#fff",
        "border-radius:6px",
        "box-shadow:0 20px 60px rgba(0,0,0,.35)",
        "padding:16px",
    ].join(";");

    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-label", "Close");
    button.textContent = "x";
    button.style.cssText = [
        "position:absolute",
        "top:8px",
        "right:10px",
        "z-index:1",
        "border:0",
        "background:rgba(255,255,255,.9)",
        "font-size:24px",
        "line-height:1",
        "cursor:pointer",
    ].join(";");

    const image = document.createElement("img");
    image.src = fullSizeImageUrl(src);
    image.alt = alt || "Product image";
    image.style.cssText = [
        "display:block",
        "max-width:calc(96vw - 64px)",
        "max-height:calc(92vh - 32px)",
        "object-fit:contain",
    ].join(";");

    button.addEventListener("click", closeOverlay);
    overlay.addEventListener("click", (event) => {
        if (event.target === overlay) {
            closeOverlay();
        }
    });

    panel.appendChild(button);
    panel.appendChild(image);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
}

document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        closeOverlay();
    }
});

document.addEventListener(
    "click",
    (event) => {
        const image = event.target.closest("img");
        if (!image) {
            return;
        }

        const field = image.closest('[name="image_1920"].o_field_widget');
        const form = image.closest(".o_form_view");
        const src = image.getAttribute("src") || "";
        if (!field || !form || form.classList.contains("o_form_editable") || !src.includes("/web/image/")) {
            return;
        }

        event.preventDefault();
        event.stopPropagation();
        showOverlay(src, image.alt);
    },
    true
);

ensureStyle();
