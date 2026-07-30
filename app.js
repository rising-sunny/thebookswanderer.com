/**
 * The Books Wanderer — homepage interactions.
 * No dependencies. Degrades cleanly if JS fails to load.
 */
(function () {
    "use strict";

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

    /* ---------- Catalog from API ---------- */
    const productGrid = document.getElementById("productGrid");
    const escapeHtml = (s) =>
        String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");

    function productUrl(p) {
        const slug = encodeURIComponent(p.slug || "");
        return slug ? `/product.html?slug=${slug}` : `/product.html?id=${p.id}`;
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
        // Cache-bust: replace existing v= or append
        let imgSrc = img;
        if (imgSrc) {
            imgSrc = imgSrc.replace(/([?&])v=[^&]*/, "$1v=" + id);
            if (!/[?&]v=/.test(imgSrc)) {
                imgSrc += (imgSrc.includes("?") ? "&" : "?") + "v=" + id;
            }
        }
        const media = imgSrc
            ? `<img src="${imgSrc}" alt="${title}" width="800" height="1000" loading="lazy" decoding="async">`
            : `<div class="product__placeholder"><svg aria-hidden="true"><use href="#i-leaf"/></svg><span>Product photo</span></div>`;
        const cta = nVar > 1 ? "Choose design" : "View details";

        return `
<article class="product" data-product-id="${id}">
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

    async function loadCatalog() {
        if (!productGrid) return;
        try {
            const res = await fetch("/api/products", { headers: { Accept: "application/json" } });
            if (!res.ok) throw new Error("catalog " + res.status);
            const data = await res.json();
            const products = data.products || [];
            if (!products.length) {
                productGrid.innerHTML =
                    '<p class="catalog-empty">New pieces are being curated — check back soon.</p>';
                return;
            }
            productGrid.innerHTML = products.map(renderProduct).join("");
            productGrid.classList.add("is-visible");
        } catch (err) {
            console.warn("catalog load failed", err);
            productGrid.innerHTML =
                '<p class="catalog-empty">Could not load products. Please refresh.</p>';
        }
    }

    loadCatalog();

    /* ---------- Cart (demo: counter only; checkout UI next) ---------- */
    const cartCount = document.getElementById("cartCount");
    const cartBtn = document.getElementById("cartBtn");
    let count = 0;

    document.addEventListener("click", (e) => {
        const btn = e.target.closest("[data-add-to-cart]");
        if (!btn || !cartCount) return;

        count += 1;
        cartCount.textContent = String(count);
        cartCount.dataset.count = String(count);
        if (cartBtn) {
            const itemWord = count === 1 ? "item" : "items";
            cartBtn.setAttribute("aria-label", `Shopping cart, ${count} ${itemWord}`);
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

    /* ---------- Newsletter (no backend yet) ---------- */
    const form = document.getElementById("newsletterForm");
    const status = document.getElementById("formStatus");

    if (form && status) {
        form.addEventListener("submit", (e) => {
            e.preventDefault();
            const email = form.querySelector("input[type=email]");

            if (!email.value || !email.checkValidity()) {
                status.textContent = "Please check your email — it looks incomplete.";
                email.focus();
                return;
            }

            // TODO: send to your provider (Mailchimp, Klaviyo, Resend…).
            status.textContent = "You're in! Check your inbox to confirm.";
            form.reset();
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
