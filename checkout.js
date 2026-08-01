/**
 * Checkout: address form + shipping quote + PayPal redirect.
 */
(function () {
    "use strict";

    const root = document.getElementById("checkoutRoot");
    if (!root || !window.TBWCart) return;

    const Cart = window.TBWCart;
    const params = new URLSearchParams(window.location.search);
    const status = (params.get("status") || "").toLowerCase();
    const orderId = params.get("order_id") || "";

    let destinations = [];
    let quote = null;
    let quoteStatus = "idle"; // idle | loading | ok | error
    let preview = null;
    let submitting = false;

    const STATUS_COPY = {
        success: {
            tone: "ok",
            title: "Thank you — payment received",
            body: "We’re preparing your order. A confirmation is on its way to your email.",
        },
        already_paid: {
            tone: "ok",
            title: "This order is already paid",
            body: "No further action is needed. Check your email for details.",
        },
        paid_cj_pending: {
            tone: "warn",
            title: "Payment received — fulfillment pending",
            body: "Your payment went through. We’re finalizing shipping with our partner; you’ll get a follow-up soon.",
        },
        cancel: {
            tone: "muted",
            title: "Checkout cancelled",
            body: "No charge was made. You can resume checkout whenever you’re ready.",
        },
        payment_error: {
            tone: "warn",
            title: "Payment could not be completed",
            body: "Something went wrong with PayPal. Please try again or use another method.",
        },
        payment_incomplete: {
            tone: "warn",
            title: "Payment incomplete",
            body: "PayPal did not confirm the payment. Please try checkout again.",
        },
    };

    function escapeHtml(s) {
        return Cart.escapeHtml(s);
    }
    function money(n) {
        return Cart.money(n);
    }

    function bannerHtml() {
        const info = STATUS_COPY[status];
        if (!info) return "";
        if (status === "success" || status === "already_paid" || status === "paid_cj_pending") {
            try {
                Cart.clear();
            } catch (_) {
                /* ignore */
            }
        }
        return `
<div class="checkout-banner checkout-banner--${info.tone}" role="status">
  <h1>${escapeHtml(info.title)}</h1>
  <p>${escapeHtml(info.body)}${
            orderId ? ` <span class="checkout-banner__id">Order #${escapeHtml(orderId)}</span>` : ""
        }</p>
  <div class="checkout-banner__actions">
    <a class="btn" href="/#featured">Back to shop</a>
    ${
        status === "cancel" || status === "payment_error" || status === "payment_incomplete"
            ? `<a class="btn btn--ghost" href="/cart.html">Return to cart</a>`
            : ""
    }
  </div>
</div>`;
    }

    function formValues() {
        const g = (id) => document.getElementById(id)?.value?.trim() || "";
        const code = g("coCountry");
        const dest = destinations.find((d) => d.code === code);
        return {
            email: g("coEmail"),
            customer_name: g("coName"),
            phone: g("coPhone"),
            shipping_address: g("coAddress"),
            shipping_address2: g("coAddress2"),
            shipping_city: g("coCity"),
            shipping_province: g("coProvince"),
            shipping_zip: g("coZip"),
            shipping_country: dest?.name || code,
            shipping_country_code: code,
        };
    }

    function cartPayload() {
        return Cart.read().map((x) => ({
            product_id: x.product_id,
            variant_id: x.variant_id,
            quantity: x.quantity,
        }));
    }

    async function loadDestinations() {
        try {
            const res = await fetch("/api/shipping/destinations", {
                headers: { Accept: "application/json" },
            });
            if (!res.ok) throw new Error("dest");
            const data = await res.json();
            destinations = data.destinations || [];
        } catch (_) {
            destinations = [
                { code: "US", name: "United States" },
                { code: "CL", name: "Chile" },
                { code: "GB", name: "United Kingdom" },
                { code: "DE", name: "Germany" },
                { code: "ES", name: "Spain" },
                { code: "AU", name: "Australia" },
            ];
        }
    }

    async function loadPreview() {
        const items = Cart.read();
        if (!items.length) {
            preview = { items: [], product_total: 0, count: 0 };
            return;
        }
        preview = await Cart.preview(items);
    }

    async function loadQuote() {
        const code = document.getElementById("coCountry")?.value || "";
        const zip = document.getElementById("coZip")?.value?.trim() || "";
        const items = cartPayload();
        if (!code || !items.length) {
            quote = null;
            quoteStatus = "idle";
            patchTotals();
            return;
        }
        quoteStatus = "loading";
        quote = null;
        patchTotals();
        try {
            const res = await fetch("/api/shipping/quote", {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    country_code: code,
                    zip_code: zip || null,
                    items,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || "quote failed");
            quote = data;
            quoteStatus = "ok";
            try {
                localStorage.setItem(Cart.SHIP_KEY, code);
            } catch (_) {
                /* ignore */
            }
        } catch (err) {
            console.warn(err);
            quote = { message: String(err.message || err) };
            quoteStatus = "error";
        }
        patchTotals();
    }

    function patchTotals() {
        const sub = document.getElementById("coSubtotal");
        const ship = document.getElementById("coShip");
        const grand = document.getElementById("coGrand");
        const eta = document.getElementById("coEta");
        const productTotal = preview?.product_total || 0;
        if (sub) sub.textContent = money(productTotal);

        if (ship) {
            if (quoteStatus === "loading") {
                ship.innerHTML = `<span class="pdp__ship-muted">Calculating…</span>`;
            } else if (quoteStatus === "error") {
                ship.innerHTML = `<span class="pdp__ship-warn">${escapeHtml(
                    quote?.message || "Unavailable"
                )}</span>`;
            } else if (quoteStatus === "ok" && quote) {
                ship.innerHTML = `<strong>${money(quote.shipping_total)}</strong>`;
            } else {
                ship.innerHTML = `<span class="pdp__ship-muted">Select country</span>`;
            }
        }

        if (eta) {
            if (quoteStatus === "ok" && quote?.eta_days) {
                eta.hidden = false;
                eta.textContent = `Estimated transit ${quote.eta_days} days (+1–3 prep)`;
            } else {
                eta.hidden = true;
                eta.textContent = "";
            }
        }

        if (grand) {
            const g =
                quoteStatus === "ok" && quote
                    ? quote.grand_total
                    : productTotal;
            grand.textContent = money(g);
        }
    }

    function renderForm() {
        const items = (preview?.items || []).filter((i) => i.available);
        if (!items.length) {
            root.innerHTML = `
<div class="cart-empty">
  <h1>Nothing to check out</h1>
  <p>Your cart is empty. Add a piece from the collection first.</p>
  <a class="btn" href="/#featured">Browse the shop</a>
</div>`;
            return;
        }

        const savedCountry = (() => {
            try {
                return localStorage.getItem(Cart.SHIP_KEY) || "";
            } catch (_) {
                return "";
            }
        })();

        const opts = destinations
            .map(
                (d) =>
                    `<option value="${escapeHtml(d.code)}"${
                        d.code === savedCountry ? " selected" : ""
                    }>${escapeHtml(d.name)}</option>`
            )
            .join("");

        const lines = items
            .map(
                (l) => `
<li class="checkout-line">
  <span class="checkout-line__img">${
      l.image_url
          ? `<img src="${escapeHtml(l.image_url)}" alt="">`
          : ""
  }</span>
  <span class="checkout-line__meta">
    <strong>${escapeHtml(l.title)}</strong>
    <span>× ${l.quantity}</span>
  </span>
  <span class="checkout-line__price">${money(l.line_total)}</span>
</li>`
            )
            .join("");

        root.innerHTML = `
<div class="checkout-layout">
  <form class="checkout-form" id="checkoutForm" novalidate>
    <header class="cart-head">
      <h1>Checkout</h1>
      <p class="cart-head__meta">Secure payment with PayPal</p>
    </header>

    <fieldset class="checkout-fieldset">
      <legend>Contact</legend>
      <label class="field">
        <span>Email</span>
        <input id="coEmail" name="email" type="email" required autocomplete="email" placeholder="you@example.com">
      </label>
      <label class="field">
        <span>Full name</span>
        <input id="coName" name="name" type="text" required autocomplete="name" minlength="2" placeholder="As on the parcel">
      </label>
      <label class="field">
        <span>Phone <em>(optional)</em></span>
        <input id="coPhone" name="phone" type="tel" autocomplete="tel" placeholder="+1 …">
      </label>
    </fieldset>

    <fieldset class="checkout-fieldset">
      <legend>Shipping address</legend>
      <label class="field">
        <span>Country</span>
        <select id="coCountry" name="country" required>
          <option value="">Choose country…</option>
          ${opts}
        </select>
      </label>
      <label class="field">
        <span>Address</span>
        <input id="coAddress" name="address" type="text" required autocomplete="address-line1" minlength="3">
      </label>
      <label class="field">
        <span>Apartment, suite <em>(optional)</em></span>
        <input id="coAddress2" name="address2" type="text" autocomplete="address-line2">
      </label>
      <div class="field-row">
        <label class="field">
          <span>City</span>
          <input id="coCity" name="city" type="text" required autocomplete="address-level2">
        </label>
        <label class="field">
          <span>State / province</span>
          <input id="coProvince" name="province" type="text" required autocomplete="address-level1">
        </label>
      </div>
      <label class="field">
        <span>Postal code</span>
        <input id="coZip" name="zip" type="text" autocomplete="postal-code">
      </label>
    </fieldset>

    <p class="checkout-error" id="coError" hidden></p>

    <button class="btn checkout-pay" type="submit" id="coSubmit">
      Pay with PayPal
    </button>
    <a class="btn btn--ghost" href="/cart.html">Back to cart</a>
  </form>

  <aside class="cart-summary checkout-summary">
    <h2>Your order</h2>
    <ul class="checkout-lines">${lines}</ul>
    <div class="cart-summary__row">
      <span>Subtotal</span>
      <strong id="coSubtotal">${money(preview.product_total)}</strong>
    </div>
    <div class="cart-summary__row">
      <span>Shipping</span>
      <span id="coShip"><span class="pdp__ship-muted">Select country</span></span>
    </div>
    <p class="pdp__ship-eta" id="coEta" hidden></p>
    <div class="cart-summary__row cart-summary__row--grand">
      <span>Total</span>
      <strong id="coGrand">${money(preview.product_total)}</strong>
    </div>
    <p class="cart-summary__note">You’ll complete payment securely on PayPal. Shipping is recalculated on our server before charge.</p>
  </aside>
</div>`;

        const form = document.getElementById("checkoutForm");
        document.getElementById("coCountry")?.addEventListener("change", loadQuote);
        document.getElementById("coZip")?.addEventListener("change", loadQuote);
        form?.addEventListener("submit", onSubmit);

        if (savedCountry) loadQuote();
    }

    async function onSubmit(e) {
        e.preventDefault();
        if (submitting) return;
        const errEl = document.getElementById("coError");
        const btn = document.getElementById("coSubmit");
        const vals = formValues();
        const items = cartPayload();

        const showErr = (msg) => {
            if (!errEl) return;
            errEl.hidden = false;
            errEl.textContent = msg;
        };
        if (errEl) {
            errEl.hidden = true;
            errEl.textContent = "";
        }

        if (!items.length) {
            showErr("Your cart is empty.");
            return;
        }
        if (!vals.email || !vals.customer_name || !vals.shipping_address) {
            showErr("Please fill in email, name, and address.");
            return;
        }
        if (!vals.shipping_country_code || !vals.shipping_city || !vals.shipping_province) {
            showErr("Please complete city, province/state, and country.");
            return;
        }
        if (quoteStatus !== "ok" || !quote) {
            showErr("Select a country with available shipping before paying.");
            return;
        }

        submitting = true;
        if (btn) {
            btn.disabled = true;
            btn.textContent = "Redirecting to PayPal…";
        }

        try {
            const res = await fetch("/api/checkout", {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    ...vals,
                    items,
                    logistic_name: quote.logistic_name || "",
                    shipping_total: quote.shipping_total,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                const detail = data.detail;
                const msg =
                    typeof detail === "string"
                        ? detail
                        : Array.isArray(detail)
                          ? detail.map((d) => d.msg || d).join("; ")
                          : "Checkout failed";
                throw new Error(msg);
            }
            if (!data.checkout_url) throw new Error("No PayPal URL returned");
            try {
                if (window.tbwTrack) {
                    window.tbwTrack("payment_redirect", {
                        value: Number(data.grand_total || quote?.grand_total) || undefined,
                        extra: { order_id: data.order_id },
                    });
                }
            } catch (_) {
                /* ignore */
            }
            window.location.href = data.checkout_url;
        } catch (err) {
            console.warn(err);
            showErr(err.message || "Checkout failed. Try again.");
            submitting = false;
            if (btn) {
                btn.disabled = false;
                btn.textContent = "Pay with PayPal";
            }
        }
    }

    async function boot() {
        // Status return from PayPal — show result, don't require cart
        if (status && STATUS_COPY[status]) {
            root.innerHTML = bannerHtml();
            Cart.paintBadge();
            try {
                if (
                    window.tbwTrack &&
                    (status === "success" ||
                        status === "already_paid" ||
                        status === "paid_cj_pending")
                ) {
                    window.tbwTrack("purchase", {
                        extra: { order_id: orderId || null, status },
                    });
                }
            } catch (_) {
                /* ignore */
            }
            return;
        }

        root.innerHTML = `<p class="catalog-loading">Preparing checkout…</p>`;
        try {
            await Promise.all([loadDestinations(), loadPreview()]);
            renderForm();
            Cart.paintBadge();
            try {
                if (window.tbwTrack) {
                    window.tbwTrack("checkout_start", {
                        value: Number(preview?.product_total) || 0,
                        extra: { lines: (preview?.items || []).length },
                    });
                }
            } catch (_) {
                /* ignore */
            }
        } catch (err) {
            console.warn(err);
            root.innerHTML = `<p class="catalog-empty">Could not load checkout. <a href="/cart.html">Back to cart</a></p>`;
        }
    }

    boot();
})();
