// Run with TBW_BROWSER_TEST_MODULES pointing to a node_modules with acorn@8.15.0.
// Loads the real descriptionHtml and escapeHtml from product.js; no browser or network.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const modules = process.env.TBW_BROWSER_TEST_MODULES;
if (!modules) throw new Error("Set TBW_BROWSER_TEST_MODULES");
const acorn = require(path.join(modules, "acorn"));
const code = fs.readFileSync(path.join(__dirname, "..", "product.js"), "utf8");
const ast = acorn.parse(code, { ecmaVersion: "latest" });
const wrapper = ast.body.find(n =>
    n.type === "ExpressionStatement" && n.expression.type === "CallExpression" &&
    n.expression.callee.type === "FunctionExpression");
assert(wrapper, "Product script wrapper not found");
const body = wrapper.expression.callee.body.body;
const escapeNode = body.find(n => n.type === "VariableDeclaration" && n.declarations.some(d => d.id.name === "escapeHtml"));
const fn = body.find(n => n.type === "FunctionDeclaration" && n.id.name === "descriptionHtml");
assert(escapeNode && fn, "escapeHtml or descriptionHtml not found");
const descriptionHtml = new Function(`${code.slice(escapeNode.start, escapeNode.end)}\n${code.slice(fn.start, fn.end)}\nreturn descriptionHtml;`)();

// Paragraphs, bullets and an ALL-CAPS heading, as the store writes them.
assert.equal(
    descriptionHtml("Intro line.\n\nWhat's inside (2 pages):\n• One\n• Two & three\n\nDETAILS\n- Size: 10 cm\n- Care: hand wash\n\nLast words."),
    "<p>Intro line.</p><p>What's inside (2 pages):</p><ul><li>One</li><li>Two &amp; three</li></ul>" +
    '<h2 class="pdp__lead-h">DETAILS</h2><ul><li>Size: 10 cm</li><li>Care: hand wash</li></ul><p>Last words.</p>',
);
// A list directly after a paragraph line, and Spanish capitals.
assert.equal(descriptionHtml("Hola:\n• Uno\nFin"), "<p>Hola:</p><ul><li>Uno</li></ul><p>Fin</p>");
assert.equal(descriptionHtml("PREPARACIÓN DEL PEDIDO\nHecho bajo pedido."), '<h2 class="pdp__lead-h">PREPARACIÓN DEL PEDIDO</h2><p>Hecho bajo pedido.</p>');
// Line breaks inside a paragraph are kept (print-on-demand copy used pre-line before).
assert.equal(descriptionHtml("Line one\r\nLine two"), "<p>Line one<br>Line two</p>");
// Escaping, and nothing to show.
assert.equal(descriptionHtml('<script>alert("x")</script>'), "<p>&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</p>");
assert.equal(descriptionHtml(""), "");
assert.equal(descriptionHtml(null), "");
// A lowercase line is never a heading; a hyphenated word is not a bullet.
assert.equal(descriptionHtml("Details\nwell-made"), "<p>Details<br>well-made</p>");
console.log("product description tests passed");
