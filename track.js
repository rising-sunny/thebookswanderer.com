/**
 * Live tracking for /admin/live (The Books Wanderer) + Meta Pixel bridge.
 * Fail-silent if the API is down or the pixel fails to load.
 *
 * The self-hosted funnel is the source of truth: Meta standard events are
 * derived from the same tbwTrack() calls, so a new event only has to be
 * added in one place (see META_EVENTS below).
 */
(function () {
    "use strict";
    try {
        var SID_KEY = "tbw_sid";
        var ATTR_KEY = "tbw_attr";
        var SITE_HOST = "thebookswanderer.com";

        var sid = localStorage.getItem(SID_KEY);
        if (!sid) {
            sid = (Date.now().toString(36) + Math.random().toString(36).slice(2, 10)).slice(0, 32);
            localStorage.setItem(SID_KEY, sid);
        }
        window.tbwSession = sid;

        var qs = new URLSearchParams(location.search);
        var paidKeys = [
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
            "fbclid",
            "gclid",
            "ttclid",
            "msclkid",
            "wbraid",
            "gbraid",
        ];
        var hasPaidSignal = paidKeys.some(function (k) {
            return qs.has(k);
        });
        var attr = null;
        try {
            attr = JSON.parse(localStorage.getItem(ATTR_KEY) || "null");
        } catch (_) {
            attr = null;
        }

        var ATTR_TTL = 30 * 24 * 3600 * 1000;
        if (attr && attr.ts && Date.now() - attr.ts > ATTR_TTL) {
            attr = null;
        }

        if (!attr || hasPaidSignal) {
            var newAttr = {
                source: qs.get("utm_source") || null,
                medium: qs.get("utm_medium") || null,
                campaign: qs.get("utm_campaign") || null,
                ts: Date.now(),
            };
            if (qs.get("fbclid")) {
                newAttr.source = newAttr.source || "facebook";
                newAttr.medium = newAttr.medium || "social";
            }
            if (qs.get("gclid") || qs.get("gbraid") || qs.get("wbraid")) {
                newAttr.source = newAttr.source || "google";
                newAttr.medium = newAttr.medium || "cpc";
            }
            if (qs.get("ttclid")) {
                newAttr.source = newAttr.source || "tiktok";
                newAttr.medium = newAttr.medium || "paid_social";
            }
            if (qs.get("msclkid")) {
                newAttr.source = newAttr.source || "bing";
                newAttr.medium = newAttr.medium || "cpc";
            }
            if (!newAttr.source && document.referrer) {
                try {
                    var rh = new URL(document.referrer).hostname;
                    if (rh && rh.indexOf(SITE_HOST) === -1) {
                        newAttr.source = rh;
                        newAttr.medium = newAttr.medium || "referral";
                    }
                } catch (_) {
                    /* ignore */
                }
            }
            if (!attr || hasPaidSignal) {
                attr = newAttr;
                localStorage.setItem(ATTR_KEY, JSON.stringify(attr));
            }
        }
        window.tbwAttr = attr;

        // --- Meta Pixel ---------------------------------------------------
        var META_PIXEL_ID = "907494619068513";

        if (!window.fbq) {
            (function (f, b, e, v, n, t, s) {
                n = f.fbq = function () {
                    n.callMethod
                        ? n.callMethod.apply(n, arguments)
                        : n.queue.push(arguments);
                };
                if (!f._fbq) f._fbq = n;
                n.push = n;
                n.loaded = true;
                n.version = "2.0";
                n.queue = [];
                t = b.createElement(e);
                t.async = true;
                t.src = v;
                s = b.getElementsByTagName(e)[0];
                s.parentNode.insertBefore(t, s);
            })(window, document, "script", "https://connect.facebook.net/en_US/fbevents.js");
            // No fbq("track", "PageView") here on purpose: the pageview at the
            // bottom of this file drives it, so both systems fire from one call.
            window.fbq("init", META_PIXEL_ID);
        }

        // tbwTrack type -> Meta standard event. Types missing from this map stay
        // self-hosted only (cart_view has no sensible Meta standard equivalent).
        var META_EVENTS = {
            pageview: "PageView",
            product_view: "ViewContent",
            add_to_cart: "AddToCart",
            checkout_start: "InitiateCheckout",
            payment_redirect: "AddPaymentInfo",
            purchase: "Purchase",
        };

        function fireMeta(type, data) {
            try {
                var name = META_EVENTS[type];
                if (!name || !window.fbq) return;
                var params = {};
                if (data) {
                    if (data.value != null) {
                        params.value = data.value;
                        params.currency = "USD";
                    }
                    if (data.product_slug) {
                        params.content_ids = [data.product_slug];
                        params.content_type = "product";
                    }
                    if (data.extra && data.extra.lines != null) {
                        params.num_items = data.extra.lines;
                    }
                }
                // Purchase goes out twice: from here without an amount (the return
                // page only knows the order id) and from the server with the real
                // total via the Conversions API. Sharing one id lets Meta keep a
                // single conversion — see server/services/meta_capi.py.
                var opts;
                if (data && data.extra && data.extra.order_id) {
                    opts = { eventID: "purchase-" + data.extra.order_id };
                }
                window.fbq("track", name, params, opts);
            } catch (_) {
                /* pixel must never break the self-hosted funnel */
            }
        }

        window.tbwTrack = function (type, data) {
            fireMeta(type, data);

            var body = {
                type: type,
                session_id: sid,
                path: location.pathname + location.search,
                referrer: document.referrer || null,
            };
            if (attr) {
                if (attr.source) body.source = attr.source;
                if (attr.medium) body.medium = attr.medium;
                if (attr.campaign) body.campaign = attr.campaign;
            }
            if (data) {
                if (data.product_slug) body.product_slug = data.product_slug;
                if (data.value != null) body.value = data.value;
                if (data.extra) body.extra = data.extra;
            }
            var json = JSON.stringify(body);
            try {
                fetch("/api/track", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: json,
                    keepalive: true,
                }).catch(function () {});
                return;
            } catch (_) {
                /* fall through */
            }
            try {
                if (navigator.sendBeacon) {
                    navigator.sendBeacon("/api/track", new Blob([json], { type: "application/json" }));
                }
            } catch (__) {
                /* ignore */
            }
        };

        // Auto pageview (skip pure success shells that re-track purchase below)
        window.tbwTrack("pageview");
    } catch (e) {
        /* fail silent */
    }
})();
