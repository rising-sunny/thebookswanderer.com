/**
 * Product detail — variants + shipping quote by country (CJ freight).
 */
(function () {
    "use strict";

    const root = document.getElementById("pdpRoot");
    const crumb = document.getElementById("pdpCrumb");
    if (!root) return;

    const params = new URLSearchParams(window.location.search);
    const slug = params.get("slug") || "";
    const id = params.get("id") || "";

    let product = null;
    let selectedVariantId = null;
    let destinations = [];
    let selectedCountry = "";
    let shippingQuote = null;
    let shippingStatus = "idle"; // idle | loading | ok | unavailable | error
    let shipSeq = 0;

    const escapeHtml = (s) =>
        String(s ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");

    function selectedVariant() {
        const variants = product?.variants || [];
        return variants.find((v) => v.id === selectedVariantId) || variants[0] || null;
    }

    function stageMain() {
        const v = selectedVariant();
        return v?.image_url || product.image_url || "";
    }

    function lifestyleImages() {
        const raw = product.lifestyle_images || product.images || [];
        const variantUrls = new Set(
            (product.variants || []).map((x) => x.image_url).filter(Boolean)
        );
        return raw.filter((u) => u && !variantUrls.has(u));
    }

    function unitPrice() {
        const v = selectedVariant();
        return Number(v?.price_usd ?? product.price_usd ?? 0);
    }

    function money(n) {
        if (n == null || Number.isNaN(n)) return "—";
        return `$${Number(n).toFixed(2)}`;
    }

    /** CJ transit range + default warehouse prep (1–3 days). */
    const PREP_MIN = 1;
    const PREP_MAX = 3;

    function deliveryRangeLabel(etaDays) {
        if (!etaDays) return "";
        const m = String(etaDays).match(/(\d+)\s*[-–—to]+\s*(\d+)/i);
        if (m) {
            const lo = Number(m[1]) + PREP_MIN;
            const hi = Number(m[2]) + PREP_MAX;
            return `Delivery ${lo}–${hi} days`;
        }
        const single = String(etaDays).match(/(\d+)/);
        if (single) {
            const n = Number(single[1]);
            return `Delivery ${n + PREP_MIN}–${n + PREP_MAX} days`;
        }
        return `Delivery ${etaDays} days`;
    }

    function shippingBlockHtml() {
        const price = unitPrice();
        const opts = destinations
            .map(
                (d) =>
                    `<option value="${escapeHtml(d.code)}"${
                        d.code === selectedCountry ? " selected" : ""
                    }>${escapeHtml(d.name)}</option>`
            )
            .join("");

        let shipLine = `<span class="pdp__ship-muted">Select a country to see shipping</span>`;
        let etaLine = "";
        let total = price;

        if (shippingStatus === "loading") {
            shipLine = `<span class="pdp__ship-muted">Calculating shipping…</span>`;
        } else if (shippingStatus === "unavailable") {
            shipLine = `<span class="pdp__ship-warn">${escapeHtml(
                shippingQuote?.message || "Not available to this country"
            )}</span>`;
        } else if (shippingStatus === "error") {
            shipLine = `<span class="pdp__ship-warn">Could not calculate shipping. Try again.</span>`;
        } else if (shippingStatus === "ok" && shippingQuote) {
            shipLine = `<strong>${money(shippingQuote.shipping_total)}</strong> <small>USD</small>`;
            // Transit (CJ) + default prep 1–3 days; no carrier name
            etaLine = shippingQuote.eta_days
                ? `<p class="pdp__ship-eta">${escapeHtml(deliveryRangeLabel(shippingQuote.eta_days))}</p>`
                : `<p class="pdp__ship-eta">Delivery ${PREP_MIN}–${PREP_MAX}+ days (incl. prep)</p>`;
            total = shippingQuote.grand_total;
        }

        return `
<div class="pdp__variants pdp__shipping" id="pdpShipping">
  <h2 class="pdp__variants-title">Shipping</h2>
  <p class="pdp__variants-label">Paid separately — rate depends on destination</p>
  <label class="pdp__ship-label" for="pdpCountry">Ship to</label>
  <select id="pdpCountry" class="pdp__ship-select" aria-label="Destination country">
    <option value="">Choose country…</option>
    ${opts}
  </select>
  <div class="pdp__totals" aria-live="polite">
    <div class="pdp__total-row">
      <span>Product</span>
      <span><strong id="pdpProductLine">${money(price)}</strong> <small>USD</small></span>
    </div>
    <div class="pdp__total-row">
      <span>Shipping</span>
      <span id="pdpShipLine">${shipLine}</span>
    </div>
    ${etaLine}
    <div class="pdp__total-row pdp__total-row--grand">
      <span>Total</span>
      <span><strong id="pdpGrandLine">${money(total)}</strong> <small>USD</small></span>
    </div>
  </div>
</div>`;
    }

    function render() {
        const title = product.title || "Product";
        const v = selectedVariant();
        const main = stageMain();
        const price = unitPrice().toFixed(2);
        const cat = product.category || "Collection";
        const variants = product.variants || [];
        const lifestyle = lifestyleImages();

        document.title = `${title} | The Books Wanderer`;
        if (crumb) crumb.textContent = title;

        const variantPicker =
            variants.length > 1
                ? `
<div class="pdp__variants">
  <h2 class="pdp__variants-title">Choose your design</h2>
  <p class="pdp__variants-label">Selected: <strong id="pdpVariantName">${escapeHtml(v?.name || "")}</strong></p>
  <div class="pdp__variant-grid" role="listbox" aria-label="Choose design">
    ${variants
        .map(
            (opt) => `
<button type="button" role="option"
  class="pdp__variant${opt.id === selectedVariantId ? " is-selected" : ""}"
  data-variant-id="${opt.id}"
  aria-selected="${opt.id === selectedVariantId ? "true" : "false"}"
  title="${escapeHtml(opt.name)}">
  <img src="${escapeHtml(opt.image_url || product.image_url || "")}" alt="${escapeHtml(opt.name)}" loading="lazy">
  <span>${escapeHtml(opt.name)}</span>
</button>`
        )
        .join("")}
  </div>
</div>`
                : variants.length === 1
                  ? `<p class="pdp__variant-single">Option: <strong>${escapeHtml(variants[0].name)}</strong></p>`
                  : "";

        const lifestyleBox =
            lifestyle.length > 0
                ? `
<div class="pdp__variants pdp__lifestyle">
  <h2 class="pdp__variants-title">In the reading nook</h2>
  <p class="pdp__variants-label">How it looks in real spaces — tap a photo to enlarge</p>
  <div class="pdp__variant-grid pdp__lifestyle-grid" role="list">
    ${lifestyle
        .map(
            (src, i) => `
<button type="button" class="pdp__variant pdp__life-shot" data-life-src="${escapeHtml(src)}" aria-label="View lifestyle photo ${i + 1}">
  <img src="${escapeHtml(src)}" alt="Product in use, photo ${i + 1}" loading="lazy">
</button>`
        )
        .join("")}
  </div>
</div>`
                : "";

        const desc = escapeHtml(product.description || "");
        const sku = v?.cj_sku || product.cj_sku || "";
        const videoUrl = product.video_url || "";
        const videoPoster = product.video_poster || main || "";

        const videoBox = videoUrl
            ? `
<div class="pdp__variants pdp__video">
  <h2 class="pdp__variants-title">See it in motion</h2>
  <p class="pdp__variants-label">Short demo — how the finger buckle holds the page</p>
  <div class="pdp__video-wrap">
    <video
      id="pdpVideo"
      class="pdp__video-el"
      controls
      playsinline
      preload="metadata"
      poster="${escapeHtml(videoPoster)}"
      src="${escapeHtml(videoUrl)}">
      Your browser does not support the video tag.
    </video>
  </div>
</div>`
            : "";

        root.innerHTML = `
<div class="pdp__info">
  <p class="eyebrow">${escapeHtml(cat)}</p>
  <h1>${escapeHtml(title)}</h1>
  <p class="pdp__price"><strong id="pdpPrice">$${price}</strong> <small>USD</small></p>
  ${desc ? `<p class="pdp__lead">${desc}</p>` : ""}
  ${variantPicker}
  ${videoBox}
  ${lifestyleBox}
  ${shippingBlockHtml()}
  <div class="pdp__actions">
    <button class="btn" type="button" data-add-to-cart
      data-product-id="${product.id}"
      data-variant-id="${v?.id || ""}">
      Add to cart
    </button>
    <a class="btn btn--ghost" href="/#featured">Continue shopping</a>
  </div>
  <ul class="pdp__meta">
    <li>Secure checkout with PayPal</li>
    <li>Gift-ready packaging</li>
    <li>Shipping calculated by destination</li>
    ${sku ? `<li id="pdpSku">SKU ${escapeHtml(sku)}</li>` : ""}
  </ul>
</div>
<div class="pdp__gallery">
  <div class="pdp__stage">
    <img id="pdpMain" src="${escapeHtml(main)}" alt="${escapeHtml(title)}${v?.name ? " — " + escapeHtml(v.name) : ""}">
  </div>
</div>`;

        root.removeAttribute("aria-busy");
        bindUi();
    }

    async function loadShippingQuote() {
        if (!product || !selectedCountry) {
            shippingQuote = null;
            shippingStatus = "idle";
            patchShippingUi();
            return;
        }
        const seq = ++shipSeq;
        shippingStatus = "loading";
        shippingQuote = null;
        patchShippingUi();

        try {
            const v = selectedVariant();
            const q = new URLSearchParams({
                country_code: selectedCountry,
                quantity: "1",
            });
            if (v?.id) q.set("variant_id", String(v.id));
            const res = await fetch(
                `/api/products/${product.id}/shipping?${q}`,
                { headers: { Accept: "application/json" } }
            );
            if (!res.ok) throw new Error("status " + res.status);
            const data = await res.json();
            if (seq !== shipSeq) return;
            shippingQuote = data;
            shippingStatus = data.available ? "ok" : "unavailable";
        } catch (err) {
            console.warn("shipping quote failed", err);
            if (seq !== shipSeq) return;
            shippingQuote = null;
            shippingStatus = "error";
        }
        patchShippingUi();
    }

    /** Update shipping lines without full page re-render (keeps select focus). */
    function patchShippingUi() {
        const panel = document.getElementById("pdpShipping");
        if (!panel) return;
        // Rebuild only shipping block content by re-rendering whole page is simpler but loses focus.
        // Update rows in place:
        const productLine = document.getElementById("pdpProductLine");
        const shipLine = document.getElementById("pdpShipLine");
        const grandLine = document.getElementById("pdpGrandLine");
        const price = unitPrice();
        if (productLine) productLine.innerHTML = money(price);

        if (shipLine) {
            if (shippingStatus === "loading") {
                shipLine.innerHTML = `<span class="pdp__ship-muted">Calculating shipping…</span>`;
            } else if (shippingStatus === "unavailable") {
                shipLine.innerHTML = `<span class="pdp__ship-warn">${escapeHtml(
                    shippingQuote?.message || "Not available to this country"
                )}</span>`;
            } else if (shippingStatus === "error") {
                shipLine.innerHTML = `<span class="pdp__ship-warn">Could not calculate shipping. Try again.</span>`;
            } else if (shippingStatus === "ok" && shippingQuote) {
                shipLine.innerHTML = `<strong>${money(
                    shippingQuote.shipping_total
                )}</strong> <small>USD</small>`;
            } else {
                shipLine.innerHTML = `<span class="pdp__ship-muted">Select a country to see shipping</span>`;
            }
        }

        let eta = panel.querySelector(".pdp__ship-eta");
        if (shippingStatus === "ok" && shippingQuote) {
            const text = shippingQuote.eta_days
                ? deliveryRangeLabel(shippingQuote.eta_days)
                : `Delivery ${PREP_MIN}–${PREP_MAX}+ days (incl. prep)`;
            if (!eta) {
                eta = document.createElement("p");
                eta.className = "pdp__ship-eta";
                const totals = panel.querySelector(".pdp__totals");
                const grand = panel.querySelector(".pdp__total-row--grand");
                if (totals && grand) totals.insertBefore(eta, grand);
                else if (totals) totals.appendChild(eta);
            }
            eta.textContent = text;
        } else if (eta) {
            eta.remove();
        }

        if (grandLine) {
            const total =
                shippingStatus === "ok" && shippingQuote
                    ? shippingQuote.grand_total
                    : price;
            grandLine.innerHTML = money(total);
        }

        const priceEl = document.getElementById("pdpPrice");
        if (priceEl) priceEl.textContent = `$${price.toFixed(2)}`;
    }

    function bindUi() {
        root.querySelectorAll(".pdp__variant[data-variant-id]").forEach((btn) => {
            btn.addEventListener("click", () => {
                selectedVariantId = Number(btn.getAttribute("data-variant-id"));
                shippingQuote = null;
                shippingStatus = selectedCountry ? "loading" : "idle";
                render();
                if (selectedCountry) loadShippingQuote();
            });
        });

        root.querySelectorAll(".pdp__life-shot").forEach((btn) => {
            btn.addEventListener("click", () => {
                const src = btn.getAttribute("data-life-src");
                const mainImg = document.getElementById("pdpMain");
                if (mainImg && src) mainImg.src = src;
                root.querySelectorAll(".pdp__life-shot").forEach((b) =>
                    b.classList.remove("is-selected")
                );
                btn.classList.add("is-selected");
            });
        });

        const countrySel = document.getElementById("pdpCountry");
        if (countrySel) {
            countrySel.addEventListener("change", () => {
                selectedCountry = countrySel.value || "";
                loadShippingQuote();
            });
        }

        root.querySelector("[data-add-to-cart]")?.addEventListener("click", (e) => {
            const btn = e.currentTarget;
            const original = btn.textContent;
            btn.textContent = "Added ✓";
            btn.classList.add("is-added");
            try {
                const cart = JSON.parse(localStorage.getItem("tbw:cart") || "[]");
                const pid = Number(btn.getAttribute("data-product-id"));
                const vid = Number(btn.getAttribute("data-variant-id")) || null;
                const existing = cart.find(
                    (x) => x.product_id === pid && x.variant_id === vid
                );
                if (existing) existing.quantity += 1;
                else cart.push({ product_id: pid, variant_id: vid, quantity: 1 });
                localStorage.setItem("tbw:cart", JSON.stringify(cart));
                if (selectedCountry) {
                    localStorage.setItem("tbw:ship_country", selectedCountry);
                }
            } catch (_) {
                /* ignore */
            }
            setTimeout(() => {
                btn.textContent = original;
                btn.classList.remove("is-added");
            }, 1600);
        });
    }

    async function loadDestinations() {
        try {
            const res = await fetch("/api/shipping/destinations", {
                headers: { Accept: "application/json" },
            });
            if (!res.ok) throw new Error("dest " + res.status);
            const data = await res.json();
            destinations = data.destinations || [];
        } catch (err) {
            console.warn(err);
            destinations = [
                { code: "US", name: "United States" },
                { code: "CL", name: "Chile" },
                { code: "GB", name: "United Kingdom" },
                { code: "DE", name: "Germany" },
                { code: "ES", name: "Spain" },
                { code: "AU", name: "Australia" },
            ];
        }
        try {
            selectedCountry = localStorage.getItem("tbw:ship_country") || "";
        } catch (_) {
            selectedCountry = "";
        }
    }

    async function load() {
        if (!slug && !id) {
            root.innerHTML = `<p class="catalog-empty">Product not found. <a href="/#featured">Back to shop</a></p>`;
            return;
        }
        try {
            const path = slug
                ? `/api/products/by-slug/${encodeURIComponent(slug)}`
                : `/api/products/${encodeURIComponent(id)}`;
            const [prodRes] = await Promise.all([
                fetch(path, { headers: { Accept: "application/json" } }),
                loadDestinations(),
            ]);
            if (!prodRes.ok) throw new Error("status " + prodRes.status);
            product = await prodRes.json();
            selectedVariantId =
                product.default_variant_id ||
                (product.variants && product.variants[0] && product.variants[0].id) ||
                null;
            render();
            if (selectedCountry) loadShippingQuote();
        } catch (err) {
            console.warn(err);
            root.innerHTML = `<p class="catalog-empty">Could not load this product. <a href="/#featured">Back to shop</a></p>`;
        }
    }

    load();
})();
