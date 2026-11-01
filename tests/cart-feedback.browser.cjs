
// Run with TBW_BROWSER_TEST_MODULES pointing to an isolated node_modules
// containing playwright@1.56.1 and acorn@8.15.0.
// Uses real cart code and product action functions, with fixture product data
// and a stub for the unrelated product-summary panel. No live website is used.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const modules = process.env.TBW_BROWSER_TEST_MODULES;
if (!modules) throw new Error("Set TBW_BROWSER_TEST_MODULES");
const { chromium } = require(path.join(modules, "playwright"));
const acorn = require(path.join(modules, "acorn"));
const root = path.resolve(__dirname, "..");
const productCode = fs.readFileSync(path.join(root, "product.js"), "utf8");
const cartCode = fs.readFileSync(path.join(root, "cart.js"), "utf8");
const css = fs.readFileSync(path.join(root, "styles.css"), "utf8");
const ast = acorn.parse(productCode, { ecmaVersion: "latest" });
const wrapper = ast.body.find(n =>
    n.type === "ExpressionStatement" &&
    n.expression.type === "CallExpression" &&
    n.expression.callee.type === "FunctionExpression"
);
assert(wrapper, "Product script wrapper not found");
const body = wrapper.expression.callee.body.body;
const functions = [
    "normVid", "selectedVariant", "cartLinesForProduct", "qtyInCartForVariant",
    "variantNameById", "cartCopy", "cartFeedbackHtml", "showCartFeedback",
    "addBarHtml", "bindAddBar", "refreshCartUi", "paintAvailability",
].map(name => {
    const node = body.find(n => n.type === "FunctionDeclaration" && n.id.name === name);
    assert(node, "Missing function: " + name);
    return productCode.slice(node.start, node.end);
}).join("\n");
const escapeNode = body.find(n =>
    n.type === "VariableDeclaration" &&
    n.declarations.some(d => d.id.name === "escapeHtml")
);
assert(escapeNode, "Missing escaping helper");

const productFixture = `
(function () {
    const root = document.getElementById("pdpRoot");
    const slug = "fixture-book";
    const product = {
        id: 1, slug, title: "Fixture book", price_usd: 19.99,
        variants: [{id: 11, name: "English", price_usd: 19.99}]
    };
    let selectedVariantId = 11, addQty = 1, selectedCountry = "";
    let cartFeedback = null;
    ${productCode.slice(escapeNode.start, escapeNode.end)}
    ${functions}
    function shipsToSelected() { return true; }
    function loadShippingQuote() {}
    function cartPanelHtml() { return '<div id="pdpCartPanel"></div>'; }
    function bindCartPanel() {}
    root.innerHTML = cartPanelHtml() + addBarHtml();
    bindAddBar(root.querySelector(".pdp__actions--cart"));
    window.fixtureRefresh = refreshCartUi;
})();
`;
const fixtureLine = {
    available: true, product_id: 1, variant_id: 11, quantity: 1,
    slug: "fixture-book", title: "Fixture book", product_title: "Fixture book",
    name: "Fixture book", variant_name: "English", image_url: "",
    price_usd: 19.99, unit_price: 19.99, unit_price_usd: 19.99,
    line_total: 19.99, line_total_usd: 19.99, subtotal: 19.99,
    supplier: "digital", from_country: "US",
};
let browser;

async function fixture(options = {}) {
    const context = await browser.newContext({
        viewport: {width: options.width || 375, height: 812},
        isMobile: (options.width || 375) < 700,
        hasTouch: (options.width || 375) < 700,
        serviceWorkers: "block",
    });
    const preview = {fails: !!options.previewFails};
    await context.route("**/*", async route => {
        const url = new URL(route.request().url());
        if (url.hostname !== "tbw.test") return route.abort();
        if (url.pathname === "/api/cart/preview") {
            if (preview.fails) return route.fulfill({status: 503, body: "fixture failure"});
            return route.fulfill({
                status: 200, contentType: "application/json",
                body: JSON.stringify({
                    items: [fixtureLine], product_total: 19.99, count: 1,
                }),
            });
        }
        if (route.request().isNavigationRequest()) {
            return route.fulfill({
                contentType: "text/html",
                body: `<!doctype html><html lang="${options.lang || "en"}">
                <head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
                <body><main id="${options.cartPage ? "cartRoot" : "pdpRoot"}"></main></body></html>`,
            });
        }
        return route.abort();
    });
    await context.addInitScript(opts => {
        const items = opts.quantity
            ? [{product_id: 1, variant_id: 11, quantity: opts.quantity}] : [];
        localStorage.setItem("tbw:cart", JSON.stringify(items));
        window.fixtureEvents = [];
        window.tbwTrack = (type, data) => {
            if (opts.analyticsThrows) throw new Error("fixture analytics failure");
            window.fixtureEvents.push({type, data});
        };
        const originalSet = Storage.prototype.setItem;
        const originalGet = Storage.prototype.getItem;
        Storage.prototype.setItem = function (key, value) {
            if (key === "tbw:cart" && opts.blockWrite) throw new Error("fixture storage failure");
            if (key === "tbw:cart" && opts.ignoreWrite) return;
            return originalSet.call(this, key, value);
        };
        Storage.prototype.getItem = function (key) {
            if (key === "tbw:cart" && opts.blockRead) throw new Error("fixture storage failure");
            return originalGet.call(this, key);
        };
    }, options);
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", e => errors.push(e.stack || e.message));
    await page.goto("https://tbw.test/" + (options.cartPage ? "cart.html" : "products/fixture-book"));
    await page.addStyleTag({content: css});
    await page.addScriptTag({content: cartCode});
    if (!options.cartPage) {
        if (options.missingCart) await page.evaluate(() => { delete window.TBWCart; });
        await page.addScriptTag({content: productFixture});
        if (errors.length) {
            throw new Error("Product fixture initialization failed:\n" + errors.join("\n"));
        }
        await page.evaluate(() => {
            if (typeof window.fixtureRefresh !== "function") {
                throw new Error("Fixture initialization did not finish");
            }
        });
    }
    return {
        page, preview,
        async close() {
            await context.close();
            assert.deepEqual(errors, [], "Unhandled browser errors");
        },
    };
}
async function events(page, type) {
    return page.evaluate(t => window.fixtureEvents.filter(e => e.type === t), type);
}
async function add(page, quantity = 1) {
    await page.locator("[data-add-qty]").fill(String(quantity));
    await page.locator("[data-add-to-cart]").click();
}
async function test(name, fn) {
    await fn();
    console.log("PASS:", name);
}

(async () => {
    browser = await chromium.launch({
        executablePath: process.env.TBW_TEST_CHROMIUM || "/snap/bin/chromium",
        headless: true, args: ["--no-sandbox"],
    });
    try {
        for (const [width, lang] of [[375, "en"], [320, "es"], [1280, "en"]]) {
            await test(`Persistent confirmation and cart link: ${width}px ${lang}`, async () => {
                const f = await fixture({width, lang});
                await add(f.page);
                await f.page.waitForTimeout(1700);
                await f.page.evaluate(() => window.fixtureRefresh());
                const feedback = f.page.locator("[data-cart-feedback]");
                assert.equal(await feedback.getAttribute("role"), "status");
                const link = feedback.locator("a");
                assert.equal(await link.getAttribute("href"), lang === "es" ? "/es/cart.html" : "/cart.html");
                await link.scrollIntoViewIfNeeded();
                assert(await link.isVisible());
                const box = await link.boundingBox();
                assert(box && box.width >= 24 && box.height >= 24);
                assert(box.x >= -1 && box.x + box.width <= width + 1, "Cart link overflows viewport");
                const recorded = await events(f.page, "add_to_cart");
                assert.equal(recorded.length, 1);
                assert.equal(recorded[0].data.extra.quantity, 1);
                assert.equal(recorded[0].data.value, 19.99);
                assert.equal(await f.page.evaluate(() => window.TBWCart.read()[0].quantity), 1);
                await f.close();
            });
        }
        for (const options of [
            {missingCart: true}, {blockWrite: true}, {ignoreWrite: true},
        ]) {
            await test("No false success: " + JSON.stringify(options), async () => {
                const f = await fixture(options);
                await add(f.page);
                assert.equal(await f.page.locator("[data-cart-feedback]").getAttribute("role"), "alert");
                assert.equal((await events(f.page, "add_to_cart")).length, 0);
                await f.close();
            });
        }
        await test("Quantity cap records only the unit actually added", async () => {
            const f = await fixture({quantity: 19});
            await add(f.page, 5);
            const recorded = await events(f.page, "add_to_cart");
            assert.equal(recorded.length, 1);
            assert.equal(recorded[0].data.extra.quantity, 1);
            assert.equal(recorded[0].data.value, 19.99);
            assert.equal(await f.page.evaluate(() => window.TBWCart.read()[0].quantity), 20);
            await add(f.page);
            assert.equal((await events(f.page, "add_to_cart")).length, 1);
            assert.equal(await f.page.locator("[data-cart-feedback]").getAttribute("role"), "alert");
            await f.close();
        });
        await test("Analytics failure does not hide a saved cart update", async () => {
            const f = await fixture({analyticsThrows: true});
            await add(f.page);
            assert.equal(await f.page.locator("[data-cart-feedback]").getAttribute("role"), "status");
            assert.equal(await f.page.evaluate(() => window.TBWCart.read()[0].quantity), 1);
            await f.close();
        });
        await test("Empty cart records opening without a loaded-cart event", async () => {
            const f = await fixture({cartPage: true});
            assert.equal((await events(f.page, "cart_open")).length, 1);
            assert.equal((await events(f.page, "cart_view")).length, 0);
            await f.close();
        });
        await test("Failed preview can retry without duplicating cart_open", async () => {
            const f = await fixture({cartPage: true, quantity: 1, previewFails: true});
            await f.page.locator("#cartRetry").waitFor();
            assert.equal((await events(f.page, "cart_open")).length, 1);
            const failed = await events(f.page, "cart_load_error");
            assert.equal(failed.length, 1);
            assert.equal(failed[0].data.extra.stage, "preview");
            f.preview.fails = false;
            await f.page.locator("#cartRetry").click();
            await f.page.waitForFunction(() => window.fixtureEvents.some(e => e.type === "cart_view"));
            assert.equal((await events(f.page, "cart_open")).length, 1);
            assert.equal((await events(f.page, "cart_view")).length, 1);
            await f.close();
        });
        for (const option of ["blockRead", "blockWrite"]) {
            await test("Cart storage error is visible: " + option, async () => {
                const f = await fixture({cartPage: true, quantity: 1, [option]: true});
                await f.page.locator("#cartRetry").waitFor();
                const failed = await events(f.page, "cart_load_error");
                assert.equal(failed.length, 1);
                assert.equal(failed[0].data.extra.stage, "storage");
                assert.equal((await events(f.page, "cart_view")).length, 0);
                await f.close();
            });
        }
    } finally {
        await browser.close();
    }
})().catch(error => {
    console.error(error);
    process.exitCode = 1;
});
