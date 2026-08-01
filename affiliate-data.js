/**
 * Amazon Associates catalog (client).
 * Data source: /affiliate-products.json (same file the server uses for SSR).
 */
(function (global) {
    "use strict";

    const FALLBACK = {
        siteDisclosure: "As an Amazon Associate I earn from qualifying purchases.",
        linkDisclosure:
            "As an Amazon Associate we earn from qualifying purchases. Amazon and the Amazon logo are trademarks of Amazon.com, Inc. or its affiliates.",
        paidLinkLabel: "paid link",
        products: [],
    };

    function install(raw) {
        const data = raw || FALLBACK;
        const products = Array.isArray(data.products) ? data.products.slice() : [];
        const SITE_DISCLOSURE = data.siteDisclosure || FALLBACK.siteDisclosure;
        const LINK_DISCLOSURE = data.linkDisclosure || FALLBACK.linkDisclosure;
        const PAID_LINK_LABEL = data.paidLinkLabel || FALLBACK.paidLinkLabel;

        function all() {
            return products.slice();
        }
        function bySlug(slug) {
            if (!slug) return null;
            const key = String(slug).toLowerCase();
            return products.find((p) => p.slug === key) || null;
        }

        global.TBW_AFFILIATE = {
            SITE_DISCLOSURE,
            LINK_DISCLOSURE,
            PAID_LINK_LABEL,
            products,
            all,
            bySlug,
            ready: true,
        };
        try {
            global.dispatchEvent(new CustomEvent("tbw-affiliate-ready"));
        } catch (_) {
            /* old browsers */
        }
    }

    // 1) SSR embed
    const embed = document.getElementById("affiliate-products-json");
    if (embed && embed.textContent.trim()) {
        try {
            install(JSON.parse(embed.textContent));
            return;
        } catch (e) {
            console.warn("affiliate embed parse failed", e);
        }
    }

    // 2) Fetch shared JSON
    fetch("/affiliate-products.json", { headers: { Accept: "application/json" } })
        .then((r) => {
            if (!r.ok) throw new Error("affiliate json " + r.status);
            return r.json();
        })
        .then(install)
        .catch((err) => {
            console.warn(err);
            install(FALLBACK);
        });
})(typeof window !== "undefined" ? window : globalThis);
