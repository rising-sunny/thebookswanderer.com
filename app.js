/**
 * The Books Wanderer — homepage interactions.
 * No dependencies. Degrades cleanly if JS fails to load.
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

    function cjImgAttrs(url, sizes, widths) {
        if (!url) return 'src=""';
        if (url.indexOf("cjdropshipping.com") === -1) return 'src="' + url + '"';
        var set = widths.map(function (w) { return cjImg(url, w) + " " + w + "w"; }).join(", ");
        return 'src="' + cjImg(url, widths[widths.length - 1]) + '" srcset="' + set +
            '" sizes="' + sizes + '"';
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    /* ---------- Header shadow on scroll ---------- */
    const header = document.getElementById("header");
    if (header) {
        const sentinel = document.createElement("div");
        sentinel.setAttribute("aria-hidden", "true");
        header.before(sentinel);

        new IntersectionObserver(
            ([entry]) => header.classList.toggle("is-stuck", !entry.isIntersecting),
            { threshold: 1 }
        ).observe(sentinel);
    }

    /* ---------- Mobile menu ---------- */
    const navToggle = document.getElementById("navToggle");
    const nav = document.getElementById("nav");

    if (navToggle && nav) {
        const iconOpen =
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18"/></svg>';
        const iconClose =
            '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>';

        const setOpen = (open) => {
            nav.dataset.open = String(open);
            navToggle.setAttribute("aria-expanded", String(open));
            navToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
            navToggle.innerHTML = open ? iconClose : iconOpen;
            document.body.classList.toggle("nav-is-open", open);
        };

        navToggle.addEventListener("click", () => {
            setOpen(nav.dataset.open !== "true");
        });

        nav.addEventListener("click", (e) => {
            if (e.target.closest("a")) setOpen(false);
        });

        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && nav.dataset.open === "true") {
                setOpen(false);
                navToggle.focus();
            }
        });

        // Close when leaving the mobile breakpoint
        const mqNav = window.matchMedia("(max-width: 980px)");
        const onNavMq = () => {
            if (!mqNav.matches && nav.dataset.open === "true") setOpen(false);
        };
        if (mqNav.addEventListener) mqNav.addEventListener("change", onNavMq);
        else mqNav.addListener(onNavMq);
    }

    /* ---------- Dismiss announcement (session-only) ---------- */
    const announcement = document.getElementById("announcement");
    if (announcement) {
        if (sessionStorage.getItem("tbw:announcement") === "dismissed") {
            announcement.hidden = true;
        }
        announcement.addEventListener("click", (e) => {
            if (!e.target.closest("[data-dismiss]")) return;
            announcement.hidden = true;
            sessionStorage.setItem("tbw:announcement", "dismissed");
        });
    }

    /* ---------- Catalog + categories from API ---------- */
    const productGrid = document.getElementById("productGrid");
    const categoryTiles = document.getElementById("categoryTiles");
    const catalogFilters = document.getElementById("catalogFilters");
    const catalogEyebrow = document.getElementById("catalogEyebrow");
    const catalogTitle = document.getElementById("catalogTitle");
    let activeCategory = "";
    let categoriesCache = [];

    const escapeHtml = (s) =>
        String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");

    function productUrl(p) {
        const slug = encodeURIComponent(p.slug || "");
        return slug ? `/products/${slug}` : `/#featured`;
    }

    function readCategoryFromUrl() {
        try {
            const params = new URLSearchParams(window.location.search);
            return (params.get("category") || "").trim().toLowerCase();
        } catch (_) {
            return "";
        }
    }

    function setCategoryInUrl(slug) {
        try {
            const url = new URL(window.location.href);
            if (slug) url.searchParams.set("category", slug);
            else url.searchParams.delete("category");
            // Keep #featured when filtering
            if (slug || window.location.hash === "#featured") {
                url.hash = "featured";
            }
            history.replaceState({}, "", url.pathname + url.search + url.hash);
        } catch (_) {
            /* ignore */
        }
    }

    function renderProduct(p, index) {
        const title = escapeHtml(p.title || "Product");
        const cat = escapeHtml(p.category || "Collection");
        const price = Number(p.price_usd || 0).toFixed(2);
        const img = escapeHtml(p.image_url || "");
        const id = p.id;
        const href = productUrl(p);
        const nVar = Number(p.variant_count || 0);
        const badge =
            nVar > 1
                ? `<span class="badge badge--gold">${nVar} designs</span>`
                : index === 0
                  ? '<span class="badge">New</span>'
                  : "";
        let imgSrc = img;
        if (imgSrc) {
            imgSrc = imgSrc.replace(/([?&])v=[^&]*/, "$1v=" + id);
            if (!/[?&]v=/.test(imgSrc)) {
                imgSrc += (imgSrc.includes("?") ? "&" : "?") + "v=" + id;
            }
        }
        const media = imgSrc
            ? `<img ${cjImgAttrs(imgSrc, "(max-width: 780px) 45vw, 300px", [400, 600, 900])} alt="${title}" width="800" height="1000" loading="lazy" decoding="async">`
            : `<div class="product__placeholder"><svg aria-hidden="true"><use href="#i-leaf"/></svg><span>Product photo</span></div>`;
        const cta = nVar > 1 ? "Choose design" : "View details";

        return `
<article class="product" data-product-id="${id}" data-category="${escapeHtml(p.category_slug || "")}">
  <a class="product__link" href="${href}" aria-label="View ${title}">
    <div class="product__media">
      ${badge}
      ${media}
    </div>
  </a>
  <div class="product__body">
    <p class="product__cat">${cat}</p>
    <h3><a href="${href}">${title}</a></h3>
    <p class="product__price">
      <strong>$${price}</strong> <small>USD</small>
      ${nVar > 1 ? `<span class="product__opts">${nVar} options</span>` : ""}
    </p>
    <a class="add-to-cart" href="${href}">${cta}</a>
  </div>
</article>`;
    }

    function renderCategoryTiles(cats) {
        if (!categoryTiles) return;
        if (!cats.length) {
            categoryTiles.innerHTML = "";
            categoryTiles.removeAttribute("aria-busy");
            return;
        }
        categoryTiles.innerHTML = cats
            .map((c) => {
                const n = Number(c.product_count || 0);
                const countLabel =
                    n === 0 ? "Coming soon" : n === 1 ? "1 product" : `${n} products`;
                const tile = escapeHtml(c.tile || "linear-gradient(150deg, #2b5240, #10241a)");
                return `
<a class="category${activeCategory === c.slug ? " is-active" : ""}"
   href="/collections/${escapeHtml(c.slug)}"
   data-category="${escapeHtml(c.slug)}"
   style="--tile: ${tile}">
  <span class="category__count">${escapeHtml(countLabel)}</span>
  <h3>${escapeHtml(c.name)}</h3>
  <p>${escapeHtml(c.description || "")}</p>
</a>`;
            })
            .join("");
        categoryTiles.removeAttribute("aria-busy");
    }

    function renderFilters(cats) {
        if (!catalogFilters) return;
        const total = cats.reduce((s, c) => s + Number(c.product_count || 0), 0);
        const chips = [
            {
                slug: "",
                name: "All",
                count: total,
            },
            ...cats,
        ];
        catalogFilters.innerHTML = chips
            .map((c) => {
                const slug = c.slug || "";
                const selected = activeCategory === slug;
                const n = Number(c.product_count != null ? c.product_count : c.count || 0);
                return `
<button type="button" role="tab"
  class="catalog-filter${selected ? " is-active" : ""}"
  data-category="${escapeHtml(slug)}"
  aria-selected="${selected ? "true" : "false"}">
  ${escapeHtml(c.name)}${n ? ` <span class="catalog-filter__n">${n}</span>` : ""}
</button>`;
            })
            .join("");
    }

    function updateCatalogHead() {
        const cat = categoriesCache.find((c) => c.slug === activeCategory);
        if (catalogEyebrow) {
            catalogEyebrow.textContent = activeCategory ? "Collection" : "Browse by";
        }
        if (catalogTitle) {
            catalogTitle.textContent = cat ? cat.name : "The shelf";
        }
    }

    async function loadCategories() {
        try {
            const res = await fetch("/api/categories", {
                headers: { Accept: "application/json" },
            });
            if (!res.ok) throw new Error("categories " + res.status);
            const data = await res.json();
            categoriesCache = data.categories || [];
        } catch (err) {
            console.warn("categories load failed", err);
            categoriesCache = [
                {
                    slug: "book-accessories",
                    name: "Book accessories",
                    description: "Page holders, bookmarks, clips for physical books.",
                    tile: "linear-gradient(150deg, #2b5240, #10241a)",
                    product_count: 0,
                },
                {
                    slug: "decor",
                    name: "Decor",
                    description: "Desk ornaments for the reading corner.",
                    tile: "linear-gradient(150deg, #c1912f, #8a5f16)",
                    product_count: 0,
                },
                {
                    slug: "ereader-accessories",
                    name: "E-reader accessories",
                    description: "Gear for Kindle and other e-readers.",
                    tile: "linear-gradient(150deg, #a63a2f, #6d221c)",
                    product_count: 0,
                },
                {
                    slug: "printables",
                    name: "Printables",
                    description: "Instant-download reading journals to print at home.",
                    tile: "linear-gradient(150deg, #3a4f7a, #1b2540)",
                    product_count: 0,
                },
            ];
        }
        renderCategoryTiles(categoriesCache);
        renderFilters(categoriesCache);
        updateCatalogHead();
    }

    async function loadCatalog() {
        if (!productGrid) return;
        productGrid.setAttribute("aria-busy", "true");
        try {
            const q = activeCategory
                ? `?category=${encodeURIComponent(activeCategory)}`
                : "";
            const res = await fetch(`/api/products${q}`, {
                headers: { Accept: "application/json" },
            });
            if (!res.ok) throw new Error("catalog " + res.status);
            const data = await res.json();
            const products = data.products || [];
            if (!products.length) {
                productGrid.innerHTML = activeCategory
                    ? `<p class="catalog-empty">Nothing in this collection yet — <a href="#featured" data-category-clear>view all pieces</a>.</p>`
                    : '<p class="catalog-empty">New pieces are being curated — check back soon.</p>';
            } else {
                productGrid.innerHTML = products.map(renderProduct).join("");
            }
            productGrid.classList.add("is-visible");
        } catch (err) {
            console.warn("catalog load failed", err);
            productGrid.innerHTML =
                '<p class="catalog-empty">Could not load products. Please refresh.</p>';
        }
        productGrid.removeAttribute("aria-busy");
        renderCategoryTiles(categoriesCache);
        renderFilters(categoriesCache);
        updateCatalogHead();
    }

    function setActiveCategory(slug, { scroll } = { scroll: false }) {
        activeCategory = (slug || "").trim().toLowerCase();
        setCategoryInUrl(activeCategory);
        loadCatalog();
        if (scroll) {
            const el = document.getElementById("featured");
            if (el) el.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
        }
    }

    document.addEventListener("click", (e) => {
        const clear = e.target.closest("[data-category-clear]");
        if (clear) {
            e.preventDefault();
            setActiveCategory("", { scroll: true });
            return;
        }
        const catBtn = e.target.closest("[data-category]");
        if (!catBtn) return;
        // Collection tiles → real SEO pages; filter chips stay on home
        if (catBtn.classList.contains("category")) {
            // Let the browser follow href="/collections/{slug}"
            return;
        }
        if (!catBtn.classList.contains("catalog-filter")) {
            return;
        }
        e.preventDefault();
        const slug = catBtn.getAttribute("data-category") || "";
        setActiveCategory(slug, { scroll: true });
    });

    activeCategory = readCategoryFromUrl();
    loadCategories().then(loadCatalog);

    /* ---------- Amazon affiliate e-reader picks ---------- */
    const affiliateGrid = document.getElementById("affiliateGrid");

    function renderAffiliateCard(p) {
        const detail = `/picks/${encodeURIComponent(p.slug)}`;
        const img = escapeHtml(p.imageUrl || "");
        const title = escapeHtml(p.shortTitle || p.title || "");
        const blurb = escapeHtml(p.blurb || "");
        const badge = p.badge
            ? `<span class="badge badge--gold">${escapeHtml(p.badge)}</span>`
            : "";
        const amazon = escapeHtml(p.amazonUrl || "#");
        return `
<article class="product product--affiliate">
  <a class="product__link" href="${detail}" aria-label="View ${title}">
    <div class="product__media pick-media">
      ${badge}
      <img src="${img}" alt="${title}" width="600" height="600" loading="lazy" decoding="async">
    </div>
  </a>
  <div class="product__body">
    <p class="product__cat">${escapeHtml(p.merchant || "Amazon")} · ${escapeHtml(p.category || "E-readers")}</p>
    <h3><a href="${detail}">${title}</a></h3>
    <p class="product__blurb-sm">${blurb}</p>
    <p class="product__price product__price--note"><strong>See price on Amazon</strong></p>
    <a class="add-to-cart"
       href="${amazon}"
       target="_blank"
       rel="nofollow sponsored noopener"
       data-affiliate="amazon"
       data-asin="${escapeHtml(p.asin || "")}">View on Amazon</a>
    <p class="paid-link-note"><span class="paid-link">(paid link)</span> · Affiliate</p>
  </div>
</article>`;
    }

    function loadAffiliatePicks() {
        if (!affiliateGrid) return;
        const A = window.TBW_AFFILIATE;
        if (!A || !A.ready || !A.all) {
            window.addEventListener("tbw-affiliate-ready", loadAffiliatePicks, {
                once: true,
            });
            // Keep SSR cards if present
            if (affiliateGrid.querySelector("[data-ssr-card]")) {
                affiliateGrid.classList.add("is-visible");
                affiliateGrid.removeAttribute("aria-busy");
            }
            return;
        }
        const list = A.all();
        if (!list.length) {
            if (!affiliateGrid.querySelector("[data-ssr-card]")) {
                affiliateGrid.innerHTML =
                    '<p class="catalog-empty">No e-reader picks yet.</p>';
            }
        } else {
            affiliateGrid.innerHTML = list.map(renderAffiliateCard).join("");
        }
        affiliateGrid.classList.add("is-visible");
        affiliateGrid.removeAttribute("aria-busy");
    }

    loadAffiliatePicks();

    /* ---------- Cart badge (shared via cart.js) ---------- */
    if (window.TBWCart) window.TBWCart.paintBadge();

    document.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-add-to-cart]");
        if (!btn) return;
        const pid = Number(btn.getAttribute("data-product-id"));
        const vid = btn.getAttribute("data-variant-id");
        if (window.TBWCart && pid) {
            window.TBWCart.add(pid, vid || null, 1);
        }
        const original = btn.textContent;
        btn.textContent = "Added ✓";
        btn.classList.add("is-added");
        setTimeout(() => {
            btn.textContent = original;
            btn.classList.remove("is-added");
        }, 1600);
    });

    /* ---------- Wishlist ---------- */
    document.addEventListener("click", (e) => {
        const heart = e.target.closest(".wishlist");
        if (!heart) return;
        const pressed = heart.getAttribute("aria-pressed") === "true";
        heart.setAttribute("aria-pressed", String(!pressed));
    });

    /* ---------- Newsletter ----------
       Antes esto no enviaba nada: validaba el email, decia "You're in! Check
       your inbox to confirm" y descartaba la direccion. No habia lista ni
       confirmacion que revisar. Ahora va a /api/newsletter/subscribe y el
       mensaje solo se muestra cuando el servidor confirma que la guardo. */
    const form = document.getElementById("newsletterForm");
    const status = document.getElementById("formStatus");

    if (form && status) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const email = form.querySelector("input[type=email]");
            const button = form.querySelector("button[type=submit]");

            if (!email.value || !email.checkValidity()) {
                status.textContent = "Please check your email — it looks incomplete.";
                email.focus();
                return;
            }

            if (button) button.disabled = true;
            status.textContent = "Adding you…";

            try {
                const res = await fetch("/api/newsletter/subscribe", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: email.value.trim() }),
                });
                if (!res.ok) throw new Error("subscribe failed");
                const data = await res.json();
                status.textContent = data.already
                    ? "You were already on the list — nothing to do."
                    : "Added. One letter a month, and a link to leave in each one.";
                form.reset();
            } catch (_) {
                status.textContent =
                    "That didn't go through. Try again, or email hello@thebookswanderer.com.";
            } finally {
                if (button) button.disabled = false;
            }
        });
    }

    /* ---------- Reveal on scroll ----------
       CSS only hides under .js-anim, so if this fails
       content stays visible by default. */
    if (!reduceMotion && "IntersectionObserver" in window) {
        const root = document.documentElement;
        root.classList.add("js-anim");

        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) return;
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                });
            },
            { rootMargin: "0px 0px -12% 0px", threshold: 0.05 }
        );

        const revealables = document.querySelectorAll(".reveal");
        revealables.forEach((el) => {
            // If already in view on load, don't wait for the observer
            const rect = el.getBoundingClientRect();
            const inView =
                rect.top < window.innerHeight * 0.92 && rect.bottom > 0;
            if (inView) el.classList.add("is-visible");
            else observer.observe(el);
        });

        // Safety net: force-show anything still hidden after 1.5s
        setTimeout(() => {
            revealables.forEach((el) => el.classList.add("is-visible"));
        }, 1500);
    }
})();
