// Offline browser regression: real challenge HTML and tracking script, mocked APIs.
// Set TBW_BROWSER_TEST_MODULES to the directory containing playwright.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(path.join(process.env.TBW_BROWSER_TEST_MODULES, 'playwright'));
const root = path.resolve(__dirname, '..');
let passed = 0;
(async () => {
 const browser = await chromium.launch({executablePath: process.env.TBW_TEST_CHROMIUM || '/usr/bin/chromium', args: ['--no-sandbox']});
 try {
  for (const [folder, lang] of [['reading-challenge-2027','en'], ['reto-de-lectura-2027','es']]) {
   for (const scenario of ['queued','not_queued','http_error','bad_result','analytics_error','invalid']) {
    const context = await browser.newContext({viewport: {width: 375, height: 812}, serviceWorkers: 'block'});
    const records = [], errors = []; let subscribed = 0;
    await context.addInitScript(() => localStorage.setItem('tbw_consent','denied'));
    await context.route('**/*', async route => {
     const url = new URL(route.request().url());
     assert.equal(url.hostname, 'tbw.test', 'External requests must not leave the fixture');
     if (url.pathname === '/api/track') {
      records.push(route.request().postDataJSON());
      return route.fulfill({json: {ok:true}});
     }
     if (url.pathname === '/api/newsletter/subscribe') {
      subscribed++;
      return route.fulfill({status: scenario === 'http_error' ? 503 : 200,
       json: {ok: scenario !== 'bad_result', already: scenario === 'not_queued', email_status: scenario === 'not_queued' ? 'not_queued' : 'queued'}});
     }
     if (url.pathname === '/track.js') return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'track.js'),'utf8')});
     if (url.pathname === `/${folder}/`) {
      // Keep the actual inline form handler; omit unrelated resources entirely.
      const html = fs.readFileSync(path.join(root,folder,'index.html'),'utf8')
       .replace(/<link\b[^>]*>/g,'').replace(/<img\b[^>]*>/g,'')
       .replace(/<script\b[^>]*src="(?!\/track\.js)[^"]*"[^>]*><\/script>/g,'');
      return route.fulfill({contentType:'text/html',body:html});
     }
     return route.abort();
    });
    const page = await context.newPage(); page.on('pageerror', e => errors.push(e.message));
    await page.goto(`https://tbw.test/${folder}/`);
    await page.waitForFunction(() => typeof window.tbwTrack === 'function');
    if (scenario === 'analytics_error') await page.evaluate(() => { window.tbwTrack = () => {throw new Error('Fixture');}; });
    await page.locator('#challengeEmail').fill(scenario === 'invalid' ? 'invalid' : 'reader@example.invalid');
    await page.locator('#challengeForm button').click();
    if (scenario === 'invalid') assert.equal(subscribed,0);
    else {
     await page.waitForFunction(() => !document.querySelector('#challengeForm button').disabled);
     const text = await page.locator('#challengeStatus').textContent();
     if (scenario === 'http_error' || scenario === 'bad_result') assert.match(text, /didn't go through|No se pudo/);
     else if (scenario === 'not_queued') assert.match(text, /No new email|No se ha programado/);
     else assert.match(text, /Request received|Solicitud recibida/);
     const requests = records.filter(r => r.type === 'challenge_request');
     assert.equal(requests.length, ['queued','not_queued'].includes(scenario) ? 1 : 0);
     if (requests.length) {
      assert.equal(requests[0].extra.lang, lang);
      assert.equal(requests[0].extra.email_status, scenario);
      assert(!JSON.stringify(requests).includes('reader@example.invalid'));
     }
    }
    if (scenario === 'queued') {
     await page.evaluate(() => {
      document.addEventListener('click', e => e.preventDefault());
      const link = document.querySelector('main a[href*="/products/"]');
      link.href += '?private=omitted'; link.click();
     });
     await page.waitForTimeout(100);
     const clicks = records.filter(r => r.type === 'challenge_product_click');
     assert.equal(clicks.length,1); assert(clicks[0].product_slug);
     assert(!JSON.stringify(clicks).includes('private=omitted'));
    }
    assert.deepEqual(errors,[]); await context.close();
    console.log(`PASS ${lang} ${scenario}`); passed++;
   }
  }
  for (const testVisit of [false, true]) {
   const context = await browser.newContext(); const records = [];
   await context.addInitScript(() => {
    localStorage.setItem('tbw_consent','granted');
    window.fixtureMeta = []; window.fbq = (...args) => window.fixtureMeta.push(args);
   });
   await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    assert.equal(url.hostname,'tbw.test');
    if (url.pathname === '/api/track') { records.push(route.request().postDataJSON()); return route.fulfill({json:{ok:true}}); }
    if (url.pathname === '/track.js') return route.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'track.js'),'utf8')});
    return route.fulfill({contentType:'text/html',body:'<html><body><script src="/track.js"></script></body></html>'});
   });
   const page = await context.newPage();
   await page.goto('https://tbw.test/checkout.html' + (testVisit ? '?tbw_test=1' : ''));
   await page.evaluate(() => window.tbwTrack('purchase_return',{extra:{order_id:123}}));
   await page.waitForTimeout(100);
   const meta = await page.evaluate(() => window.fixtureMeta);
   if (testVisit) { assert.deepEqual(records,[]); assert.deepEqual(meta,[]); }
   else {
    assert.equal(records.filter(r => r.type === 'purchase_return').length,1);
    const purchase = meta.find(r => r[1] === 'Purchase');
    assert.equal(purchase[3].eventID,'purchase-123');
   }
   await context.close(); console.log('PASS ' + (testVisit ? 'test visit excluded' : 'Meta purchase ID preserved')); passed++;
  }
 } finally { await browser.close(); }
 console.log(`${passed} browser cases passed`);
})().catch(e => {console.error(e);process.exitCode=1;});
