/**
 * Product detail — variants + shipping quote by country (CJ freight).
 */
(function () {
    "use strict";

    // CJ's CDN honours Alibaba OSS image processing, so we ask it for a
    // card-sized WebP instead of the full-resolution original. On the worst
    // image on the home page that is 743 KB down to 34 KB.
    function cjImg(url, w) {
        if (!url || url.indexOf("cjdropshipping.com") === -1) return url;
        if (url.indexOf("x-oss-process") !== -1) return url;
        return url + (url.indexOf("?") === -1 ? "?" : "&") +
            "x-oss-process=image/resize,w_" + w + "/format,webp";
    }

    function cjSrcset(url, widths) {
        if (!url || url.indexOf("cjdropshipping.com") === -1) return "";
        return widths.map(function (w) { return cjImg(url, w) + " " + w + "w"; }).join(", ");
    }

    function cjImgAttrs(url, sizes, widths) {
        if (!url) return 'src=""';
        if (url.indexOf("cjdropshipping.com") === -1) return 'src="' + url + '"';
        var set = widths.map(function (w) { return cjImg(url, w) + " " + w + "w"; }).join(", ");
        return 'src="' + cjImg(url, widths[widths.length - 1]) + '" srcset="' + set +
            '" sizes="' + sizes + '"';
    }

    const root = document.getElementById("pdpRoot");
    const crumb = document.getElementById("pdpCrumb");
    if (!root) return;

    const params = new URLSearchParams(window.location.search);
    function pathSlug(prefix) {
        const m = window.location.pathname.match(
            new RegExp("^/" + prefix + "/([^/]+)/?$", "i")
        );
        return m ? decodeURIComponent(m[1]) : "";
    }
    // Prefer pretty path /products/{slug}, then ?slug=, then SSR data-slug
    const slug =
        pathSlug("products") ||
        params.get("slug") ||
        (root.dataset && root.dataset.slug) ||
        "";
    const id = params.get("id") || root.dataset.productId || "";

    let product = null;
    let selectedVariantId = null;
    let addQty = 1; // qty to add for the currently selected variant
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

    function normVid(v) {
        if (v == null || v === "" || v === "null") return null;
        const n = Number(v);
        return Number.isFinite(n) && n > 0 ? n : null;
    }

    function selectedVariant() {
        const variants = product?.variants || [];
        return variants.find((v) => v.id === selectedVariantId) || variants[0] || null;
    }

    /** Cart lines for this product (one row per variant). */
    function cartLinesForProduct() {
        if (!product || !window.TBWCart) return [];
        const pid = Number(product.id);
        return (window.TBWCart.read() || []).filter(
            (x) => Number(x.product_id) === pid
        );
    }

    function qtyInCartForVariant(variantId) {
        const vid = normVid(variantId);
        const line = cartLinesForProduct().find(
            (x) => normVid(x.variant_id) === vid
        );
        return line ? Number(line.quantity) || 0 : 0;
    }

    function variantNameById(variantId) {
        const vid = normVid(variantId);
        const variants = product?.variants || [];
        const v = variants.find((x) => Number(x.id) === vid);
        return v?.name || (vid ? `Option ${vid}` : "Standard");
    }

    function cartPanelHtml() {
        const lines = cartLinesForProduct();
        if (!lines.length) {
            return `
<div class="pdp__cart-panel" id="pdpCartPanel" hidden>
  <h2 class="pdp__variants-title">In your cart</h2>
  <p class="pdp__variants-label">No options of this product yet. Choose a design and quantity below.</p>
</div>`;
        }
        const rows = lines
            .map((line) => {
                const vid = normVid(line.variant_id);
                const name = escapeHtml(variantNameById(vid));
                const q = Number(line.quantity) || 1;
                return `
<div class="pdp__cart-line" data-cart-pid="${product.id}" data-cart-vid="${vid ?? ""}">
  <div class="pdp__cart-line__info">
    <strong>${name}</strong>
    <span class="pdp__cart-line__meta">${q} in cart</span>
  </div>
  <div class="pdp__cart-line__acts">
    <div class="cart-qty pdp__mini-qty">
      <button type="button" class="cart-qty__btn" data-cart-act="dec" aria-label="Decrease ${name}">−</button>
      <span class="pdp__mini-qty__n" aria-live="polite">${q}</span>
      <button type="button" class="cart-qty__btn" data-cart-act="inc" aria-label="Increase ${name}">+</button>
    </div>
    <button type="button" class="cart-line__remove pdp__cart-remove" data-cart-act="remove">Remove</button>
  </div>
</div>`;
            })
            .join("");
        const totalUnits = lines.reduce((n, l) => n + (Number(l.quantity) || 0), 0);
        return `
<div class="pdp__cart-panel" id="pdpCartPanel">
  <h2 class="pdp__variants-title">In your cart</h2>
  <p class="pdp__variants-label">
    ${lines.length} option${lines.length === 1 ? "" : "s"} · ${totalUnits} item${totalUnits === 1 ? "" : "s"}.
    Each design is a separate line — change qty or remove below.
  </p>
  <div class="pdp__cart-lines">${rows}</div>
  <p class="pdp__cart-panel__foot">
    <a class="link-more" href="/cart.html">View full cart</a>
  </p>
</div>`;
    }

    function addBarHtml() {
        const v = selectedVariant();
        const inCart = qtyInCartForVariant(v?.id);
        const multi = (product.variants || []).length > 1;
        return `
<div class="pdp__actions pdp__actions--cart">
  ${
      multi
          ? `<p class="pdp__add-hint">You can add several options of this product. Each color/size is its own cart line with its own quantity.</p>`
          : ""
  }
  <div class="pdp__add-row">
    <label class="cart-qty pdp__add-qty" for="pdpAddQty">
      <span class="visually-hidden">Quantity to add</span>
      <button type="button" class="cart-qty__btn" data-add-act="dec" aria-label="Decrease quantity to add">−</button>
      <input id="pdpAddQty" type="number" min="1" max="20" value="${addQty}" data-add-qty inputmode="numeric" aria-label="Quantity to add">
      <button type="button" class="cart-qty__btn" data-add-act="inc" aria-label="Increase quantity to add">+</button>
    </label>
    <button class="btn" type="button" data-add-to-cart
      data-product-id="${product.id}"
      data-variant-id="${v?.id || ""}">
      ${inCart > 0 ? `Add ${addQty} more` : `Add ${addQty} to cart`}
    </button>
  </div>
  ${
      inCart > 0
          ? `<p class="pdp__add-status" id="pdpAddStatus"><strong>${escapeHtml(v?.name || "This option")}</strong> — ${inCart} already in cart</p>`
          : `<p class="pdp__add-status" id="pdpAddStatus" hidden></p>`
  }
  <a class="btn btn--ghost" href="/products/">Continue shopping</a>
</div>`;
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
  <p class="pdp__variants-label"><strong>Free worldwide</strong> — pick your country for the delivery estimate</p>
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

        const pageTitle = `${title} | The Books Wanderer`;
        document.title = pageTitle;
        const rawDesc = String(product.description || "")
            .replace(/[\u2018\u2019]/g, "'")
            .replace(/[\u201c\u201d]/g, '"')
            .replace(/\s+/g, " ")
            .trim();
        let meta = rawDesc;
        if (meta.length > 155) {
            meta = meta.slice(0, 154).replace(/\s+\S*$/, "").replace(/[,.;:\-]+$/, "") + "...";
        }
        const setMeta = (sel, attr, val) => {
            const el = document.querySelector(sel);
            if (el && val) el.setAttribute(attr, val);
        };
        if (meta) {
            setMeta('meta[name="description"]', "content", meta);
            setMeta('meta[property="og:description"]', "content", meta);
            setMeta('meta[name="twitter:description"]', "content", meta);
        }
        setMeta('meta[property="og:title"]', "content", pageTitle);
        setMeta('meta[name="twitter:title"]', "content", pageTitle);
        const img = stageMain() || product.image_url || "";
        if (img) {
            setMeta('meta[property="og:image"]', "content", img);
            setMeta('meta[name="twitter:image"]', "content", img);
        }
        if (crumb) crumb.textContent = title;

        const manyOpts = variants.length > 8;
        const pickerTitle = manyOpts ? "Choose color & size" : "Choose your design";
        const pickerAria = manyOpts ? "Choose color and size" : "Choose design";
        const variantPicker =
            variants.length > 1
                ? `
<div class="pdp__variants">
  <h2 class="pdp__variants-title">${pickerTitle}</h2>
  <p class="pdp__variants-label">Selected: <strong id="pdpVariantName">${escapeHtml(v?.name || "")}</strong></p>
  <div class="pdp__variant-grid${manyOpts ? " pdp__variant-grid--dense" : ""}" role="listbox" aria-label="${pickerAria}">
    ${variants
        .map(
            (opt) => `
<button type="button" role="option"
  class="pdp__variant${opt.id === selectedVariantId ? " is-selected" : ""}"
  data-variant-id="${opt.id}"
  aria-selected="${opt.id === selectedVariantId ? "true" : "false"}"
  title="${escapeHtml(opt.name)}">
  <img ${cjImgAttrs(escapeHtml(opt.image_url || product.image_url || ""), "90px", [200, 400])} alt="${escapeHtml(opt.name)}" loading="lazy" decoding="async">
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
  <img ${cjImgAttrs(escapeHtml(src), "(max-width: 780px) 45vw, 380px", [400, 600])} alt="Product in use, photo ${i + 1}" loading="lazy" decoding="async">
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
  ${cartPanelHtml()}
  ${addBarHtml()}
  ${videoBox}
  ${lifestyleBox}
  ${shippingBlockHtml()}
  <ul class="pdp__meta">
    <li>Free shipping worldwide — no cost added at checkout</li>
    <li>Secure checkout with PayPal</li>
    <li>Faulty or wrong items refunded in full</li>
    ${sku ? `<li id="pdpSku">SKU ${escapeHtml(sku)}</li>` : ""}
  </ul>
</div>
<div class="pdp__gallery">
  <div class="pdp__stage">
    <img id="pdpMain" ${cjImgAttrs(escapeHtml(main), "(max-width: 780px) 92vw, 480px", [400, 600, 900])} alt="${escapeHtml(title)}${v?.name ? " — " + escapeHtml(v.name) : ""}">
  </div>
</div>`;

        root.removeAttribute("aria-busy");
        bindUi();
    }

    /** Refresh only cart panel + add bar without full re-render (keeps shipping select). */
    function refreshCartUi() {
        const panel = document.getElementById("pdpCartPanel");
        const wrap = document.createElement("div");
        wrap.innerHTML = cartPanelHtml().trim();
        const nextPanel = wrap.firstElementChild;
        if (panel && nextPanel) panel.replaceWith(nextPanel);
        else if (nextPanel && !panel) {
            const picker = root.querySelector(".pdp__variants");
            picker?.after(nextPanel);
        }

        const actions = root.querySelector(".pdp__actions--cart");
        const wrap2 = document.createElement("div");
        wrap2.innerHTML = addBarHtml().trim();
        const nextActions = wrap2.firstElementChild;
        if (actions && nextActions) {
            actions.replaceWith(nextActions);
            bindAddBar(nextActions);
        }
        bindCartPanel();
        if (window.TBWCart) window.TBWCart.paintBadge();
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

    function bindAddBar(scope) {
        const el = scope || root;
        const qtyInput = el.querySelector("[data-add-qty]");
        el.querySelector('[data-add-act="dec"]')?.addEventListener("click", () => {
            addQty = Math.max(1, addQty - 1);
            if (qtyInput) qtyInput.value = String(addQty);
            const btn = el.querySelector("[data-add-to-cart]");
            if (btn) {
                const inCart = qtyInCartForVariant(selectedVariant()?.id);
                btn.textContent =
                    inCart > 0 ? `Add ${addQty} more` : `Add ${addQty} to cart`;
            }
        });
        el.querySelector('[data-add-act="inc"]')?.addEventListener("click", () => {
            addQty = Math.min(20, addQty + 1);
            if (qtyInput) qtyInput.value = String(addQty);
            const btn = el.querySelector("[data-add-to-cart]");
            if (btn) {
                const inCart = qtyInCartForVariant(selectedVariant()?.id);
                btn.textContent =
                    inCart > 0 ? `Add ${addQty} more` : `Add ${addQty} to cart`;
            }
        });
        qtyInput?.addEventListener("change", () => {
            addQty = Math.max(1, Math.min(20, Number(qtyInput.value) || 1));
            qtyInput.value = String(addQty);
        });

        el.querySelector("[data-add-to-cart]")?.addEventListener("click", (e) => {
            const btn = e.currentTarget;
            const original = btn.textContent;
            try {
                const pid = Number(btn.getAttribute("data-product-id"));
                const vid = normVid(btn.getAttribute("data-variant-id"));
                const q = Math.max(
                    1,
                    Math.min(20, Number(qtyInput?.value) || addQty || 1)
                );
                addQty = q;
                if (window.TBWCart) {
                    window.TBWCart.add(pid, vid, q);
                }
                try {
                    if (window.tbwTrack && product) {
                        const v = selectedVariant();
                        const unit = Number(v?.price_usd ?? product.price_usd) || 0;
                        window.tbwTrack("add_to_cart", {
                            product_slug: product.slug || slug || "",
                            value: Math.round(unit * q * 100) / 100,
                            extra: { quantity: q, variant_id: vid },
                        });
                    }
                } catch (_) {
                    /* ignore */
                }
                if (selectedCountry) {
                    try {
                        localStorage.setItem("tbw:ship_country", selectedCountry);
                    } catch (_) {
                        /* ignore */
                    }
                }
                btn.textContent = `Added ${q} ✓`;
                btn.classList.add("is-added");
                refreshCartUi();
            } catch (_) {
                /* ignore */
            }
            setTimeout(() => {
                if (!btn.isConnected) return;
                const inCart = qtyInCartForVariant(selectedVariant()?.id);
                btn.textContent =
                    inCart > 0 ? `Add ${addQty} more` : `Add ${addQty} to cart`;
                btn.classList.remove("is-added");
            }, 1400);
        });
    }

    function bindCartPanel() {
        root.querySelectorAll(".pdp__cart-line").forEach((row) => {
            const pid = Number(row.getAttribute("data-cart-pid"));
            const vid = normVid(row.getAttribute("data-cart-vid"));
            row.querySelector('[data-cart-act="dec"]')?.addEventListener("click", () => {
                if (!window.TBWCart) return;
                const cur = qtyInCartForVariant(vid);
                if (cur <= 1) window.TBWCart.remove(pid, vid);
                else window.TBWCart.setQty(pid, vid, cur - 1);
                refreshCartUi();
            });
            row.querySelector('[data-cart-act="inc"]')?.addEventListener("click", () => {
                if (!window.TBWCart) return;
                const cur = qtyInCartForVariant(vid);
                window.TBWCart.setQty(pid, vid, Math.min(20, cur + 1));
                refreshCartUi();
            });
            row.querySelector('[data-cart-act="remove"]')?.addEventListener(
                "click",
                () => {
                    if (!window.TBWCart) return;
                    window.TBWCart.remove(pid, vid);
                    refreshCartUi();
                }
            );
        });
    }

    function bindUi() {
        root.querySelectorAll(".pdp__variant[data-variant-id]").forEach((btn) => {
            btn.addEventListener("click", () => {
                selectedVariantId = Number(btn.getAttribute("data-variant-id"));
                addQty = 1;
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
                // srcset wins over src, so swapping only src would keep the
                // previous photo on screen. Rebuild both.
                if (mainImg && src) {
                    mainImg.srcset = cjSrcset(src, [400, 600, 900]);
                    mainImg.src = cjImg(src, 900);
                }
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

        bindAddBar();
        bindCartPanel();
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
            root.innerHTML = `<p class="catalog-empty">Product not found. <a href="/products/">Back to shop</a></p>`;
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
            try {
                if (window.tbwTrack) {
                    window.tbwTrack("product_view", {
                        product_slug: product.slug || slug || "",
                        value: Number(product.price_usd) || undefined,
                    });
                }
            } catch (_) {
                /* ignore */
            }
            render();
            if (selectedCountry) loadShippingQuote();
        } catch (err) {
            console.warn(err);
            // Keep server-rendered SEO body if present (avoids Soft 404 after failed hydrate)
            if (root.querySelector("[data-ssr]")) {
                root.removeAttribute("aria-busy");
                return;
            }
            root.innerHTML = `<p class="catalog-empty">Could not load this product. <a href="/products/">Back to shop</a></p>`;
        }
    }

    load();
})();
