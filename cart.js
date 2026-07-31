/**
 * Shared cart (localStorage) + cart page renderer.
 * Storage key: tbw:cart → [{ product_id, variant_id|null, quantity }]
 */
(function (global) {
    "use strict";

    const KEY = "tbw:cart";
    const SHIP_KEY = "tbw:ship_country";

    function escapeHtml(s) {
        return String(s ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function read() {
        try {
            const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
            if (!Array.isArray(raw)) return [];
            return raw
                .map((x) => ({
                    product_id: Number(x.product_id),
                    variant_id: x.variant_id != null && x.variant_id !== ""
                        ? Number(x.variant_id)
                        : null,
                    quantity: Math.max(1, Math.min(20, Number(x.quantity) || 1)),
                }))
                .filter((x) => x.product_id > 0);
        } catch (_) {
            return [];
        }
    }

    function write(items) {
        localStorage.setItem(KEY, JSON.stringify(items));
        paintBadge();
        try {
            global.dispatchEvent(new CustomEvent("tbw:cart-change", { detail: { items } }));
        } catch (_) {
            /* ignore */
        }
    }

    function countItems(items) {
        return (items || read()).reduce((n, x) => n + (x.quantity || 0), 0);
    }

    function add(productId, variantId, qty) {
        const items = read();
        const pid = Number(productId);
        const vid =
            variantId != null && variantId !== "" ? Number(variantId) : null;
        const q = Math.max(1, Math.min(20, Number(qty) || 1));
        const existing = items.find(
            (x) => x.product_id === pid && x.variant_id === vid
        );
        if (existing) existing.quantity = Math.min(20, existing.quantity + q);
        else items.push({ product_id: pid, variant_id: vid, quantity: q });
        write(items);
        return items;
    }

    function setQty(productId, variantId, qty) {
        const items = read();
        const pid = Number(productId);
        const vid =
            variantId != null && variantId !== "" ? Number(variantId) : null;
        const q = Math.max(0, Math.min(20, Number(qty) || 0));
        const next = items
            .map((x) => {
                if (x.product_id === pid && x.variant_id === vid) {
                    return { ...x, quantity: q };
                }
                return x;
            })
            .filter((x) => x.quantity > 0);
        write(next);
        return next;
    }

    function remove(productId, variantId) {
        return setQty(productId, variantId, 0);
    }

    function clear() {
        write([]);
    }

    function paintBadge() {
        const n = countItems();
        document.querySelectorAll("#cartCount, .cart-count").forEach((el) => {
            el.textContent = String(n);
            el.dataset.count = String(n);
            if (el.hasAttribute("aria-hidden")) {
                el.setAttribute("aria-hidden", n === 0 ? "true" : "false");
            }
        });
        document.querySelectorAll("#cartBtn, [data-cart-btn]").forEach((btn) => {
            const word = n === 1 ? "item" : "items";
            btn.setAttribute(
                "aria-label",
                n ? `Shopping cart, ${n} ${word}` : "Shopping cart, empty"
            );
        });
    }

    async function preview(items) {
        const payload = { items: items || read() };
        if (!payload.items.length) {
            return { items: [], product_total: 0, count: 0 };
        }
        const res = await fetch("/api/cart/preview", {
            method: "POST",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("cart preview " + res.status);
        return res.json();
    }

    function money(n) {
        if (n == null || Number.isNaN(n)) return "—";
        return `$${Number(n).toFixed(2)}`;
    }

    // ---- Cart page ----
    async function renderCartPage() {
        const root = document.getElementById("cartRoot");
        if (!root) return;

        const raw = read();
        if (!raw.length) {
            root.innerHTML = `
<div class="cart-empty">
  <h1>Your cart is empty</h1>
  <p>Wander the collection and add something for your next reading hour.</p>
  <a class="btn" href="/#featured">Continue shopping</a>
</div>`;
            paintBadge();
            return;
        }

        root.innerHTML = `<p class="catalog-loading">Loading cart…</p>`;
        let data;
        try {
            data = await preview(raw);
        } catch (err) {
            console.warn(err);
            root.innerHTML = `<p class="catalog-empty">Could not load cart. <button type="button" class="btn" id="cartRetry">Retry</button></p>`;
            document.getElementById("cartRetry")?.addEventListener("click", renderCartPage);
            return;
        }

        const lines = data.items || [];
        const available = lines.filter((l) => l.available);
        // Drop unavailable from storage
        if (available.length !== raw.length) {
            write(
                available.map((l) => ({
                    product_id: l.product_id,
                    variant_id: l.variant_id,
                    quantity: l.quantity,
                }))
            );
        }
        if (!available.length) {
            clear();
            renderCartPage();
            return;
        }

        const rows = available
            .map(
                (l) => `
<article class="cart-line" data-pid="${l.product_id}" data-vid="${l.variant_id ?? ""}">
  <a class="cart-line__media" href="/product.html?slug=${encodeURIComponent(l.slug || "")}">
    ${
        l.image_url
            ? `<img src="${escapeHtml(l.image_url)}" alt="" loading="lazy">`
            : `<span class="cart-line__ph"></span>`
    }
  </a>
  <div class="cart-line__body">
    <p class="cart-line__cat">${escapeHtml(l.category || "")}</p>
    <h2 class="cart-line__title">
      <a href="/product.html?slug=${encodeURIComponent(l.slug || "")}">${escapeHtml(l.product_title || l.title)}</a>
    </h2>
    ${l.variant_name ? `<p class="cart-line__var">${escapeHtml(l.variant_name)}</p>` : ""}
    <p class="cart-line__unit">${money(l.unit_price)} <small>USD each</small></p>
    <div class="cart-line__actions">
      <label class="cart-qty">
        <span class="visually-hidden">Quantity</span>
        <button type="button" class="cart-qty__btn" data-act="dec" aria-label="Decrease quantity">−</button>
        <input type="number" min="1" max="20" value="${l.quantity}" data-qty inputmode="numeric">
        <button type="button" class="cart-qty__btn" data-act="inc" aria-label="Increase quantity">+</button>
      </label>
      <button type="button" class="cart-line__remove" data-act="remove">Remove</button>
    </div>
  </div>
  <p class="cart-line__total"><strong>${money(l.line_total)}</strong> <small>USD</small></p>
</article>`
            )
            .join("");

        root.innerHTML = `
<div class="cart-layout">
  <div class="cart-main">
    <header class="cart-head">
      <h1>Your cart</h1>
      <p class="cart-head__meta">${available.length} line${available.length === 1 ? "" : "s"} · ${data.count} item${data.count === 1 ? "" : "s"}</p>
    </header>
    <div class="cart-lines">${rows}</div>
  </div>
  <aside class="cart-summary">
    <h2>Order summary</h2>
    <div class="cart-summary__row">
      <span>Subtotal</span>
      <strong>${money(data.product_total)}</strong>
    </div>
    <p class="cart-summary__note">Shipping calculated at checkout by destination.</p>
    <a class="btn cart-summary__cta" href="/checkout.html">Proceed to checkout</a>
    <a class="btn btn--ghost cart-summary__shop" href="/#featured">Continue shopping</a>
  </aside>
</div>`;

        root.querySelectorAll(".cart-line").forEach((row) => {
            const pid = Number(row.getAttribute("data-pid"));
            const vidRaw = row.getAttribute("data-vid");
            const vid = vidRaw === "" || vidRaw == null ? null : Number(vidRaw);
            const input = row.querySelector("[data-qty]");

            row.querySelector('[data-act="dec"]')?.addEventListener("click", () => {
                const q = Math.max(1, (Number(input.value) || 1) - 1);
                setQty(pid, vid, q);
                renderCartPage();
            });
            row.querySelector('[data-act="inc"]')?.addEventListener("click", () => {
                const q = Math.min(20, (Number(input.value) || 1) + 1);
                setQty(pid, vid, q);
                renderCartPage();
            });
            input?.addEventListener("change", () => {
                setQty(pid, vid, Number(input.value) || 1);
                renderCartPage();
            });
            row.querySelector('[data-act="remove"]')?.addEventListener("click", () => {
                remove(pid, vid);
                renderCartPage();
            });
        });

        paintBadge();
    }

    // Public API
    const TBWCart = {
        KEY,
        SHIP_KEY,
        read,
        write,
        add,
        setQty,
        remove,
        clear,
        count: countItems,
        paintBadge,
        preview,
        money,
        escapeHtml,
        renderCartPage,
    };

    global.TBWCart = TBWCart;

    // Init badge on every page that includes this script
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", paintBadge);
    } else {
        paintBadge();
    }

    // Cart icon → cart page
    document.addEventListener("click", (e) => {
        const btn = e.target.closest("#cartBtn, [data-cart-btn]");
        if (!btn) return;
        // If it's a link with href to cart, let it navigate
        if (btn.tagName === "A" && btn.getAttribute("href")) return;
        e.preventDefault();
        window.location.href = "/cart.html";
    });

    // Cart page auto-render
    if (document.getElementById("cartRoot")) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", renderCartPage);
        } else {
            renderCartPage();
        }
    }
})(window);
