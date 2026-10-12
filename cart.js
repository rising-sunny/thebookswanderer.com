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

    /** Normalize variant id: missing / "" / NaN → null */
    function normVid(v) {
        if (v == null || v === "" || v === "null" || v === "undefined") return null;
        const n = Number(v);
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    function normPid(v) {
        const n = Number(v);
        return Number.isFinite(n) && n > 0 ? n : 0;
    }

    function sameLine(item, productId, variantId) {
        return (
            normPid(item.product_id) === normPid(productId) &&
            normVid(item.variant_id) === normVid(variantId)
        );
    }

    function read() {
        try {
            const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
            if (!Array.isArray(raw)) return [];
            return raw
                .map((x) => ({
                    product_id: normPid(x.product_id),
                    variant_id: normVid(x.variant_id),
                    quantity: Math.max(1, Math.min(20, Number(x.quantity) || 1)),
                }))
                .filter((x) => x.product_id > 0);
        } catch (_) {
            return [];
        }
    }

    function write(items) {
        const clean = (items || []).map((x) => ({
            product_id: normPid(x.product_id),
            variant_id: normVid(x.variant_id),
            quantity: Math.max(1, Math.min(20, Number(x.quantity) || 1)),
        })).filter((x) => x.product_id > 0);
        localStorage.setItem(KEY, JSON.stringify(clean));
        paintBadge();
        try {
            global.dispatchEvent(new CustomEvent("tbw:cart-change", { detail: { items: clean } }));
        } catch (_) {
            /* ignore */
        }
    }

    function countItems(items) {
        return (items || read()).reduce((n, x) => n + (x.quantity || 0), 0);
    }

    function add(productId, variantId, qty) {
        const items = read();
        const pid = normPid(productId);
        const vid = normVid(variantId);
        const q = Math.max(1, Math.min(20, Number(qty) || 1));
        if (!pid) return items;
        const existing = items.find((x) => sameLine(x, pid, vid));
        if (existing) existing.quantity = Math.min(20, existing.quantity + q);
        else items.push({ product_id: pid, variant_id: vid, quantity: q });
        write(items);
        return items;
    }

    function setQty(productId, variantId, qty) {
        const pid = normPid(productId);
        const vid = normVid(variantId);
        const q = Math.max(0, Math.min(20, Number(qty) || 0));
        const next = read()
            .map((x) => {
                if (sameLine(x, pid, vid)) {
                    return { ...x, quantity: q };
                }
                return x;
            })
            .filter((x) => x.quantity > 0);
        write(next);
        return next;
    }

    function remove(productId, variantId) {
        const pid = normPid(productId);
        const vid = normVid(variantId);
        const next = read().filter((x) => !sameLine(x, pid, vid));
        write(next);
        return next;
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
  <a class="btn" href="/products/">Continue shopping</a>
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
        // Sync storage to available lines only (normalize variant ids)
        write(
            available.map((l) => ({
                product_id: l.product_id,
                variant_id: normVid(l.variant_id),
                quantity: l.quantity,
            }))
        );
        if (!available.length) {
            clear();
            renderCartPage();
            return;
        }

        const rows = available
            .map((l) => {
                const vidAttr =
                    l.variant_id != null && l.variant_id !== ""
                        ? String(l.variant_id)
                        : "";
                return `
<article class="cart-line" data-pid="${l.product_id}" data-vid="${escapeHtml(vidAttr)}">
  <a class="cart-line__media" href="/products/${encodeURIComponent(l.slug || "")}">
    ${
        l.image_url
            ? `<img src="${escapeHtml(l.image_url)}" alt="${escapeHtml(l.product_title || l.title || "")}" loading="lazy">`
            : `<span class="cart-line__ph"></span>`
    }
  </a>
  <div class="cart-line__body">
    <p class="cart-line__cat">${escapeHtml(l.category || "")}</p>
    <h2 class="cart-line__title">
      <a href="/products/${encodeURIComponent(l.slug || "")}">${escapeHtml(l.product_title || l.title)}</a>
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
      <button type="button" class="cart-line__remove" data-act="remove" aria-label="Remove ${escapeHtml(l.product_title || "item")} from cart">Remove</button>
    </div>
  </div>
  <p class="cart-line__total"><strong>${money(l.line_total)}</strong> <small>USD</small></p>
</article>`;
            })
            .join("");

        root.innerHTML = `
<div class="cart-layout">
  <div class="cart-main">
    <header class="cart-head">
      <h1>Your cart</h1>
      <p class="cart-head__meta">${available.length} line${available.length === 1 ? "" : "s"} · ${data.count} item${data.count === 1 ? "" : "s"}</p>
    </header>
    <div class="cart-lines">${rows}</div>
    <p class="cart-clear-wrap">
      <button type="button" class="cart-clear" id="cartClearAll">Clear cart</button>
    </p>
  </div>
  <aside class="cart-summary">
    <h2>Order summary</h2>
    <div class="cart-summary__row">
      <span>Subtotal</span>
      <strong>${money(data.product_total)}</strong>
    </div>
    <p class="cart-summary__note">Free shipping worldwide — nothing is added at checkout.</p>
    <p class="cart-summary__note">Payment: <strong>PayPal</strong> only.</p>
    <a class="btn cart-summary__cta" href="/checkout.html">Proceed to checkout</a>
    <a class="btn btn--ghost cart-summary__shop" href="/products/">Continue shopping</a>
  </aside>
</div>`;

        try {
            if (window.tbwTrack) {
                const firstSlug = (available[0] && available[0].slug) || "";
                window.tbwTrack("cart_view", {
                    product_slug: firstSlug || undefined,
                    value: Number(data.product_total) || 0,
                    extra: { lines: available.length, items: data.count },
                });
            }
        } catch (_) {
            /* ignore */
        }

        root.querySelectorAll(".cart-line").forEach((row) => {
            const pid = normPid(row.getAttribute("data-pid"));
            const vid = normVid(row.getAttribute("data-vid"));
            const input = row.querySelector("[data-qty]");

            row.querySelector('[data-act="dec"]')?.addEventListener("click", () => {
                const cur = Number(input?.value) || 1;
                if (cur <= 1) {
                    remove(pid, vid);
                } else {
                    setQty(pid, vid, cur - 1);
                }
                renderCartPage();
            });
            row.querySelector('[data-act="inc"]')?.addEventListener("click", () => {
                const q = Math.min(20, (Number(input?.value) || 1) + 1);
                setQty(pid, vid, q);
                renderCartPage();
            });
            input?.addEventListener("change", () => {
                const q = Number(input.value) || 0;
                if (q <= 0) remove(pid, vid);
                else setQty(pid, vid, q);
                renderCartPage();
            });
            row.querySelector('[data-act="remove"]')?.addEventListener("click", (e) => {
                e.preventDefault();
                e.stopPropagation();
                remove(pid, vid);
                renderCartPage();
            });
        });

        document.getElementById("cartClearAll")?.addEventListener("click", () => {
            if (global.confirm("Remove all items from your cart?")) {
                clear();
                renderCartPage();
            }
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
        if (btn.tagName === "A" && btn.getAttribute("href")) return;
        e.preventDefault();
        window.location.href = (window.TBW_L || String)("/cart.html");
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
