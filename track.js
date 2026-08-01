/**
 * Self-hosted live tracking for /admin/live (The Books Wanderer).
 * No third-party scripts. Fail-silent if API is down.
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

        window.tbwTrack = function (type, data) {
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
