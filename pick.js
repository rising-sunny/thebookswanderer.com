/**
 * Affiliate pick PDP — Amazon Special Links (no cart / no CJ).
 * Supports multi-image gallery when product.images[] is set.
 */
(function () {
    "use strict";

    const root = document.getElementById("pickRoot");
    const crumb = document.getElementById("pickCrumb");
    const siteDisc = document.getElementById("pickSiteDisclosure");
    const linkDisc = document.getElementById("pickLinkDisclosure");
    const footerAff = document.getElementById("footerAffiliate");

    function esc(s) {
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function querySlug() {
        const q = new URLSearchParams(window.location.search);
        return (q.get("slug") || "").trim().toLowerCase();
    }

    function galleryUrls(p) {
        const list = [];
        const seen = new Set();
        const push = (u) => {
            const url = String(u || "").trim();
            if (!url || seen.has(url)) return;
            seen.add(url);
            list.push(url);
        };
        (p.images || []).forEach(push);
        push(p.imageUrl);
        return list;
    }

    function paintEmpty(msg) {
        if (root) {
            root.innerHTML = `<p class="catalog-empty">${esc(msg)}</p>`;
            root.setAttribute("aria-busy", "false");
        }
    }

    function bindGallery() {
        const main = document.getElementById("pickMain");
        const thumbs = root.querySelectorAll("[data-pick-thumb]");
        if (!main || !thumbs.length) return;

        thumbs.forEach((btn) => {
            btn.addEventListener("click", () => {
                const src = btn.getAttribute("data-src");
                if (!src) return;
                main.src = src;
                thumbs.forEach((t) => {
                    t.classList.toggle("is-active", t === btn);
                    t.setAttribute("aria-pressed", t === btn ? "true" : "false");
                });
            });
        });
    }

    function render(p, A) {
        document.title = `${p.title} | The Books Wanderer`;
        const meta = document.querySelector('meta[name="description"]');
        if (meta) {
            meta.setAttribute("content", `${p.blurb} ${A.SITE_DISCLOSURE}`);
        }
        if (crumb) crumb.textContent = p.shortTitle || p.title;
        if (siteDisc) siteDisc.textContent = A.SITE_DISCLOSURE;
        if (linkDisc) linkDisc.textContent = A.LINK_DISCLOSURE;
        if (footerAff) footerAff.textContent = A.SITE_DISCLOSURE;

        const bullets = (p.bullets || [])
            .map((b) => `<li>${esc(b)}</li>`)
            .join("");

        const pairs = (p.pairsWith || [])
            .map((x) => {
                const href = x.href
                    ? String(x.href)
                    : x.slug
                      ? `/product.html?slug=${encodeURIComponent(x.slug)}`
                      : "#";
                return `<a class="pick-pair" href="${esc(href)}">${esc(x.label || x.slug || "Related")}</a>`;
            })
            .join("");

        const pairsBlock = pairs
            ? `<div class="pick-pairs">
                <p class="eyebrow">Pairs with our shop</p>
                <div class="pick-pairs__list">${pairs}</div>
               </div>`
            : "";

        const imgs = galleryUrls(p);
        const hero = imgs[0] || p.imageUrl || "";
        const thumbsHtml =
            imgs.length > 1
                ? `<div class="pdp__thumbs" role="group" aria-label="Product photos">
                    ${imgs
                        .map(
                            (u, i) => `
                      <button type="button"
                              class="pdp__thumb${i === 0 ? " is-active" : ""}"
                              data-pick-thumb
                              data-src="${esc(u)}"
                              aria-label="Photo ${i + 1} of ${imgs.length}"
                              aria-pressed="${i === 0 ? "true" : "false"}">
                        <img src="${esc(u)}" alt="" width="120" height="120" loading="${i < 3 ? "eager" : "lazy"}">
                      </button>`
                        )
                        .join("")}
                   </div>`
                : "";

        root.innerHTML = `
            <div class="pdp__gallery">
                <div class="pdp__stage product__media pick-media">
                    <img id="pickMain" src="${esc(hero)}" alt="${esc(p.title)}" width="800" height="800" loading="eager">
                </div>
                ${thumbsHtml}
            </div>
            <div class="pdp__info">
                <p class="eyebrow">${esc(p.category || "E-readers")} · ${esc(p.merchant || "Amazon")}</p>
                ${p.badge ? `<span class="badge badge--gold pick-badge">${esc(p.badge)}</span>` : ""}
                <h1>${esc(p.title)}</h1>
                <p class="pdp__blurb">${esc(p.blurb)}</p>
                <p class="pdp__desc">${esc(p.description)}</p>
                ${bullets ? `<ul class="pick-bullets">${bullets}</ul>` : ""}

                <div class="pick-cta">
                    <a class="btn pick-cta__btn"
                       href="${esc(p.amazonUrl)}"
                       target="_blank"
                       rel="nofollow sponsored noopener"
                       data-affiliate="amazon"
                       data-asin="${esc(p.asin || "")}">
                        View on Amazon
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17 17 7M9 7h8v8"/></svg>
                    </a>
                    <p class="pick-cta__meta">
                        <span class="paid-link">(${esc(A.PAID_LINK_LABEL)})</span>
                        · Sold by Amazon · Price shown on Amazon
                    </p>
                    <p class="pick-cta__note">
                        You will leave The Books Wanderer and open Amazon.com.
                        ${esc(A.SITE_DISCLOSURE)}
                    </p>
                </div>

                ${pairsBlock}
            </div>
        `;
        root.setAttribute("aria-busy", "false");
        bindGallery();
    }

    function boot() {
        const A = window.TBW_AFFILIATE;
        if (!A) {
            paintEmpty("Affiliate catalog failed to load.");
            return;
        }
        if (footerAff) footerAff.textContent = A.SITE_DISCLOSURE;
        if (siteDisc) siteDisc.textContent = A.SITE_DISCLOSURE;
        if (linkDisc) linkDisc.textContent = A.LINK_DISCLOSURE;

        const slug = querySlug();
        if (!slug) {
            paintEmpty("Missing product. Browse our e-reader picks on the home page.");
            return;
        }
        const p = A.bySlug(slug);
        if (!p) {
            paintEmpty("We could not find that pick.");
            return;
        }
        render(p, A);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();
