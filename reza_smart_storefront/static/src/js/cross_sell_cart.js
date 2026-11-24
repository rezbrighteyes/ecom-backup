import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

/**
 * "You might also like" sidebar on the product page: the cart button on each
 * cross-sell adds that variant to the cart without leaving the page, then shows
 * a small toast.
 *
 * Odoo 20 port: this was a DOMContentLoaded IIFE posting to /shop/cart/update_json,
 * with a GET /shop/cart/update fallback. Both routes are gone on 20; adding is now
 * the JSON-RPC /shop/cart/add (product_template_id, product_id, quantity), which
 * returns cart_quantity. The fallback opens the product page instead, because no
 * GET route that adds to the cart is left.
 *
 * sunglass_superstore_product_page ships an identical copy. Both used to bind, so
 * with both modules installed one click added the item twice; both copies now
 * register under one shared key and only the first one loaded binds.
 */
export class SfCrossSellCart extends Interaction {
    static selector = "#sf_sidebar";
    dynamicContent = {
        ".sf-add-cart": { "t-on-click.prevent.stop": this.locked(this.onAddClick) },
    };

    setup() {
        this.hideTimer = null;
        this.toast = null;
    }

    start() {
        if (this.el.querySelector(".sf-add-cart")) {
            this.buildToast();
        }
    }

    destroy() {
        if (this.hideTimer) {
            clearTimeout(this.hideTimer);
        }
    }

    buildToast() {
        const toast = document.createElement("div");
        toast.style.cssText = "position:fixed;top:20px;right:20px;background:#fff;border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,0.15);padding:16px 20px;z-index:9999;display:none;min-width:280px;max-width:340px;border:1px solid rgba(0,0,0,0.08);";

        const header = document.createElement("div");
        header.style.cssText = "display:flex;align-items:center;gap:12px;margin-bottom:12px;";
        const dot = document.createElement("div");
        dot.style.cssText = "width:8px;height:8px;border-radius:50%;background:#10b981;flex-shrink:0;";
        header.appendChild(dot);
        const title = document.createElement("strong");
        title.style.fontSize = "14px";
        title.textContent = "Added to cart";
        header.appendChild(title);
        const close = document.createElement("span");
        close.style.cssText = "margin-left:auto;cursor:pointer;color:#999;font-size:18px;line-height:1;";
        close.textContent = "×";
        header.appendChild(close);

        const body = document.createElement("div");
        body.style.cssText = "display:flex;align-items:center;gap:10px;";
        this.toastImg = document.createElement("img");
        this.toastImg.style.cssText = "width:48px;height:48px;border-radius:8px;object-fit:cover;";
        const info = document.createElement("div");
        this.toastName = document.createElement("div");
        this.toastName.style.cssText = "font-size:13px;font-weight:600;";
        this.toastPrice = document.createElement("div");
        this.toastPrice.style.cssText = "font-size:14px;color:#D4AF37;font-weight:700;";
        info.appendChild(this.toastName);
        info.appendChild(this.toastPrice);
        body.appendChild(this.toastImg);
        body.appendChild(info);

        const link = document.createElement("a");
        link.href = "/shop/cart";
        link.style.cssText = "display:block;text-align:center;background:#0F1720;color:#fff;padding:10px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;margin-top:12px;";
        link.textContent = "View cart";

        toast.appendChild(header);
        toast.appendChild(body);
        toast.appendChild(link);
        this.toast = toast;
        // Removed again when the interaction stops (insert registers the cleanup).
        this.insert(toast, document.body);
        this.addListener(close, "click", () => {
            toast.style.display = "none";
        });
    }

    showToast(variantId, name, price) {
        if (!this.toast) {
            return;
        }
        this.toastImg.src = "/web/image/product.product/" + variantId + "/image_128";
        this.toastName.textContent = name;
        this.toastPrice.textContent = price;
        this.toast.style.display = "block";
        if (this.hideTimer) {
            clearTimeout(this.hideTimer);
        }
        this.hideTimer = this.waitForTimeout(() => {
            this.toast.style.display = "none";
        }, 4000);
    }

    async onAddClick(ev) {
        const btn = ev.currentTarget;
        const item = btn.closest(".sf-related-item");
        const variantId = parseInt(btn.dataset.variantId);
        const templateId = parseInt(btn.dataset.templateId);
        const fallback = () => {
            const link = item && item.querySelector("a.sf-related-link");
            window.location.href = link ? link.href : "/shop";
        };
        btn.style.opacity = "0.5";
        let result;
        try {
            result = await this.waitFor(
                rpc("/shop/cart/add", {
                    product_template_id: templateId,
                    product_id: variantId,
                    quantity: 1,
                })
            );
        } catch {
            fallback();
            return;
        }
        this.protectSyncAfterAsync(() => {
            btn.style.opacity = "1";
            if (!result) {
                fallback();
                return;
            }
            btn.style.background = "#10b981";
            btn.style.borderColor = "#10b981";
            btn.style.color = "#fff";
            for (const badge of document.querySelectorAll(".my_cart_quantity")) {
                badge.textContent = result.cart_quantity;
                badge.classList.remove("d-none");
            }
            this.showToast(variantId, item.dataset.name, item.dataset.price);
            this.waitForTimeout(() => {
                btn.style.background = "";
                btn.style.borderColor = "";
                btn.style.color = "";
            }, 2000);
        })();
    }
}

const interactions = registry.category("public.interactions");
if (!interactions.contains("sf_cross_sell_cart")) {
    interactions.add("sf_cross_sell_cart", SfCrossSellCart);
}
