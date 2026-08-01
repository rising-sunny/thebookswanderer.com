/**
 * Amazon Associates catalog (static).
 * Each product uses a Special Link with our Associate tag.
 *
 * Compliance (Associates Program Operating Agreement §5 + FTC):
 * - Site disclosure: "As an Amazon Associate I earn from qualifying purchases."
 * - Clear, conspicuous disclosure near each Special Link (paid link).
 * - Do not imply Amazon endorsement.
 */
(function (global) {
    "use strict";

    /** Official site-wide disclosure language (Amazon Associates). */
    const SITE_DISCLOSURE =
        "As an Amazon Associate I earn from qualifying purchases.";

    /**
     * Short note placed next to CTAs / cards with Special Links.
     * FTC: clear + conspicuous near the affiliate link.
     */
    const LINK_DISCLOSURE =
        "As an Amazon Associate we earn from qualifying purchases. Amazon and the Amazon logo are trademarks of Amazon.com, Inc. or its affiliates.";

    const PAID_LINK_LABEL = "paid link";

    const products = [
        {
            slug: "kindle-paperwhite",
            asin: "B0DDZJS3SB",
            title: "Kindle Paperwhite (16 GB)",
            shortTitle: "Kindle Paperwhite",
            merchant: "Amazon",
            category: "E-readers",
            badge: "Editor’s pick",
            /** Full Special Link from Associates SiteStripe (tag=modernreade08-20). */
            amazonUrl:
                "https://www.amazon.com/dp/B0DDZJS3SB?th=1&linkCode=ll2&tag=modernreade08-20&linkId=f6c6a7cc6ca1f8c8107a4f9ccaa1777a&language=es_US&gaOptInStatus=true&ref_=as_li_ss_tl",
            /** Card / default hero */
            imageUrl:
                "https://m.media-amazon.com/images/I/71YwNBmu+aL._AC_SL1500_.jpg",
            /** Gallery on pick.html (Amazon product images via media-amazon CDN). */
            images: [
                "https://m.media-amazon.com/images/I/71YwNBmu+aL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/31NUBsiULnL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41C0QG+eaqL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41+qk6tiFcL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41kZBcmnOqL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41zalyMHAQL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41mFy1zsgnL._AC_SL1500_.jpg",
            ],
            blurb:
                "The e-reader we recommend for most readers: a 7\" glare-free screen, warm light, and weeks of battery — light enough for the commute, sharp enough for late chapters.",
            description:
                "Amazon’s current Kindle Paperwhite (16 GB) is our default pick when someone asks which e-reader to buy. The larger 7\" display is easier on the eyes than the basic Kindle, the adjustable warm light works day and night, and a single USB-C charge can last for weeks. We pair it with our magnetic sleeves for travel. Prices and availability change on Amazon; you’ll see the live offer when you leave our site.",
            bullets: [
                "7\" glare-free Paperwhite display with higher contrast and faster page turns",
                "Adjustable front light (white to amber) for any room or nightstand",
                "Up to ~12 weeks of battery life on a single USB-C charge (Amazon estimate)",
                "16 GB — room for thousands of books without social apps or notifications",
                "IPX8 water resistance for baths and beach bags (per Amazon specs)",
            ],
            /** Optional: our store products that pair well (CJ catalog slugs). */
            pairsWith: [
                {
                    slug: "kindle-magnetic-sleeve",
                    label: "Kindle Magnetic Sleeve",
                },
            ],
        },
        {
            slug: "kindle",
            asin: "B0DDZQTYHL",
            title: "Kindle (16 GB)",
            shortTitle: "Kindle",
            merchant: "Amazon",
            category: "E-readers",
            badge: "Best budget",
            amazonUrl:
                "https://www.amazon.com/dp/B0DDZQTYHL?th=1&linkCode=ll2&tag=modernreade08-20&linkId=f5a086612e922e731455491af647c67e&language=es_US&gaOptInStatus=true&ref_=as_li_ss_tl",
            imageUrl:
                "https://m.media-amazon.com/images/I/71q6spMq75L._AC_SL1500_.jpg",
            images: [
                "https://m.media-amazon.com/images/I/71q6spMq75L._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41Q-lYDkLLL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/412cVV454-L._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41jfEQhBM-L._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41jl3XckXVL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/41V4Vyq8RdL._AC_SL1500_.jpg",
                "https://m.media-amazon.com/images/I/51S1qyyXtdL._AC_SL1500_.jpg",
            ],
            blurb:
                "The lightest, most compact Kindle — a 6\" glare-free screen, brighter front light, and weeks of battery for readers who want a simple, affordable e-reader.",
            description:
                "Amazon’s current Kindle (16 GB) is our budget pick and a great first e-reader. It is lighter and smaller than the Paperwhite, with a 6\" glare-free display, a brighter adjustable front light, and up to about six weeks of battery life (Amazon estimate). Perfect if you mainly read novels and want to spend less, or gift a Kindle without the Paperwhite price. For a larger screen and warmer light, step up to our Paperwhite pick. Prices on Amazon change; you’ll see the live offer when you leave our site.",
            bullets: [
                "Lightest and most compact Kindle — easy in a bag or jacket pocket",
                "6\" glare-free display with higher contrast and faster page turns",
                "Front light up to ~25% brighter at max setting, plus dark mode",
                "Up to ~6 weeks of battery life on a single charge (Amazon estimate)",
                "16 GB storage — thousands of books, no social apps or notifications",
            ],
            pairsWith: [
                {
                    slug: "kindle-magnetic-sleeve",
                    label: "Kindle Magnetic Sleeve",
                },
                {
                    slug: "kindle-paperwhite",
                    label: "Prefer a larger screen? Paperwhite",
                    href: "/pick.html?slug=kindle-paperwhite",
                },
            ],
        },
    ];

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
    };
})(typeof window !== "undefined" ? window : globalThis);
