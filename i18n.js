/**
 * Language support for The Books Wanderer.
 *
 * English pages: adds the EN/ES switcher when the server did not, and sends
 * a reader who chose Spanish before to the /es/ edition of the same page.
 *
 * Spanish pages (/es/…, <html lang="es">): the server already translated the
 * HTML it sent. Parts drawn later by app.js, product.js, cart.js and
 * checkout.js are translated here as they appear, from the same dictionary
 * (window.TBW_I18N, inlined by the server), so those scripts stay
 * English-only. API calls for products get ?lang=es, and links to pages that
 * have a Spanish edition are pointed at it.
 */
(function () {
    "use strict";

    var KEY = "tbw:lang";
    var lang = (document.documentElement.getAttribute("lang") || "en").slice(0, 2);
    var LOCALIZED = /^\/(?:$|index\.html$|#|products\/|collections(?:\/|$|\?)|(?:about|contact|privacy|shipping-returns|cart|checkout)\.html)/;

    function enPath(p) {
        if (p === "/es" || p === "/es/") return "/";
        return p.indexOf("/es/") === 0 ? p.slice(3) : p;
    }
    function esPath(p) {
        p = enPath(p);
        if (!LOCALIZED.test(p)) return p;
        if (p === "/" || p === "/index.html") return "/es/";
        return "/es" + p;
    }
    function remember(l) {
        try { localStorage.setItem(KEY, l); } catch (_) { /* private mode */ }
    }
    function saved() {
        try { return localStorage.getItem(KEY); } catch (_) { return null; }
    }

    var here = location.pathname;
    var localizable = LOCALIZED.test(enPath(here));

    // Someone who picked Spanish earlier lands on an English page.
    if (lang === "en" && localizable && saved() === "es" && !/[?&]lang=en\b/.test(location.search)) {
        location.replace(esPath(here) + location.search + location.hash);
        return;
    }

    window.TBW_LANG = lang;
    window.TBW_L = function (path) { return lang === "es" ? esPath(path) : path; };

    function addSwitcher() {
        if (!localizable || document.querySelector("[data-lang-switch]")) return;
        var actions = document.querySelector(".header .actions");
        if (!actions) return;
        var other = lang === "es" ? "en" : "es";
        var a = document.createElement("a");
        a.className = "lang-switch";
        a.href = other === "es" ? esPath(here) : enPath(here);
        a.setAttribute("hreflang", other);
        a.setAttribute("lang", other);
        a.setAttribute("data-lang-switch", other);
        a.title = other === "es" ? "Ver en español" : "View in English";
        a.textContent = other.toUpperCase();
        actions.insertBefore(a, actions.firstChild);
    }

    document.addEventListener("click", function (e) {
        var a = e.target.closest && e.target.closest("[data-lang-switch]");
        if (!a) return;
        remember(a.getAttribute("data-lang-switch"));
        a.href = a.getAttribute("href") + location.search + location.hash;
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", addSwitcher);
    } else {
        addSwitcher();
    }

    if (lang !== "es") return;

    // ── Spanish edition ────────────────────────────────────────────────
    var data = window.TBW_I18N || { phrases: {}, templates: [] };
    var phrases = data.phrases || {};
    var templates = (data.templates || []).map(function (t) {
        return [new RegExp(t[0]), t[1]];
    });

    function tr(text) {
        var norm = text.replace(/\s+/g, " ").trim();
        if (!norm) return null;
        if (Object.prototype.hasOwnProperty.call(phrases, norm)) return phrases[norm];
        for (var i = 0; i < templates.length; i++) {
            if (templates[i][0].test(norm)) return norm.replace(templates[i][0], templates[i][1]);
        }
        return null;
    }

    function fixText(node) {
        var v = node.nodeValue;
        var es = tr(v);
        if (es === null || es === v.trim()) return;
        var lead = v.match(/^\s*/)[0];
        var trail = v.match(/\s*$/)[0];
        node.nodeValue = lead + es + trail;
    }

    var ATTRS = ["alt", "aria-label", "placeholder", "title"];
    function fixElement(el) {
        if (el.tagName === "SCRIPT" || el.tagName === "STYLE") return;
        for (var i = 0; i < ATTRS.length; i++) {
            var v = el.getAttribute(ATTRS[i]);
            if (v) {
                var es = tr(v);
                if (es !== null && es !== v) el.setAttribute(ATTRS[i], es);
            }
        }
        if (el.tagName === "A" && !el.hasAttribute("data-lang-switch")) {
            var href = el.getAttribute("href");
            if (href && href.charAt(0) === "/" && href.indexOf("/es/") !== 0 && LOCALIZED.test(href)) {
                el.setAttribute("href", esPath(href));
            }
        }
    }

    function walk(root) {
        if (root.nodeType === 3) { fixText(root); return; }
        if (root.nodeType !== 1) return;
        fixElement(root);
        var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
            acceptNode: function (n) {
                var p = n.nodeType === 3 ? n.parentNode : n;
                return p && (p.tagName === "SCRIPT" || p.tagName === "STYLE")
                    ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
            },
        });
        var n;
        while ((n = w.nextNode())) {
            if (n.nodeType === 3) fixText(n); else fixElement(n);
        }
    }

    function fixTitle() {
        var es = tr(document.title);
        if (es !== null && es !== document.title) document.title = es;
    }

    new MutationObserver(function (records) {
        for (var i = 0; i < records.length; i++) {
            var r = records[i];
            if (r.type === "characterData") fixText(r.target);
            else if (r.type === "attributes") fixElement(r.target);
            else for (var j = 0; j < r.addedNodes.length; j++) walk(r.addedNodes[j]);
        }
        fixTitle();
    }).observe(document.documentElement, {
        childList: true, subtree: true, characterData: true,
        attributes: true, attributeFilter: ATTRS.concat(["href"]),
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () { walk(document.body); fixTitle(); });
    } else {
        walk(document.body);
    }

    // Product data in Spanish, and the language travels with the order.
    var origFetch = window.fetch;
    if (origFetch) {
        window.fetch = function (input, init) {
            try {
                var url = typeof input === "string" ? input : input.url;
                if (/^\/api\/(products|cart\/preview)/.test(url)) {
                    url += (url.indexOf("?") === -1 ? "?" : "&") + "lang=es";
                    if (typeof input === "string") input = url;
                    else input = new Request(url, input);
                } else if (/^\/api\/checkout(\?|$)/.test(url) && init && init.body && typeof init.body === "string") {
                    var body = JSON.parse(init.body);
                    body.lang = "es";
                    init = Object.assign({}, init, { body: JSON.stringify(body) });
                }
            } catch (_) { /* fall through untouched */ }
            return origFetch.call(this, input, init);
        };
    }
})();
