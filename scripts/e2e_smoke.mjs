// Browser smoke test against a running Aloud server. Optional; the pytest suite does not need it.
//
//   npm install playwright && npx playwright install chromium   (playwright-core also works)
//   BASE=http://localhost:8787 node scripts/e2e_smoke.mjs
//
// Walks the real UI: adds a pasted document, plays it, watches the highlight move through
// every sentence, changes the speed and the voice, and confirms progress was saved.

const { chromium } = await import('playwright').catch(() => import('playwright-core'));

const base = process.env.BASE || 'http://localhost:8787';
const launch = { args: ['--autoplay-policy=no-user-gesture-required'] };
if (process.env.CHROME) launch.executablePath = process.env.CHROME;
if (process.env.NO_SANDBOX) launch.args.push('--no-sandbox');

const browser = await chromium.launch(launch);
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
const problems = [];
page.on('console', (msg) => { if (msg.type() === 'error') problems.push(`console: ${msg.text()}`); });
page.on('pageerror', (err) => problems.push(`pageerror: ${err.message}`));
const log = (...args) => console.log('[smoke]', ...args);
const fail = (message) => { problems.push(message); log('FAIL', message); };

await page.goto(`${base}/#/`);
await page.waitForSelector('.doc-card');
await page.click('button.btn.primary:has-text("Add")');
await page.click('.tabs button:has-text("Paste text")');
await page.fill('input[placeholder="Optional title"]', 'Smoke test');
await page.fill('textarea', 'The quick brown fox jumps over the lazy dog. A second sentence follows here. And a third one closes it out.');
await page.click('button:has-text("Add text")');
await page.waitForSelector('.reader .s');
const sentences = await page.$$eval('.reader .s', (nodes) => nodes.length);
if (sentences !== 3) fail(`expected 3 sentences, saw ${sentences}`);

const status = await page.evaluate(() => fetch('/api/tts/status').then((r) => r.json()));
log('voice model:', status.state);
await page.click('.player-controls .play');
const seen = new Set();
const start = Date.now();
while (Date.now() - start < 90000) {
  const active = await page.$eval('.reader .s.active', (n) => n.dataset.i).catch(() => null);
  if (active !== null) seen.add(active);
  const meta = await page.$eval('.now-meta', (n) => n.textContent);
  if (/Finished/.test(meta)) break;
  await page.waitForTimeout(400);
}
log('sentences highlighted:', [...seen].join(', '));
if (seen.size < 3) fail('playback did not reach every sentence');

await page.click('.chip.mono');
await page.click('.presets button:has-text("2.0x")');
await page.keyboard.press('Escape');
await page.click('.chip:not(.mono)');
await page.waitForSelector('.voice-row');
const voices = await page.$$eval('.voice-row', (nodes) => nodes.length);
log('voices listed:', voices);
await page.keyboard.press('Escape');

const settings = await page.evaluate(() => fetch('/api/settings').then((r) => r.json()));
if (settings.speed !== 2) fail(`speed was not saved: ${settings.speed}`);
const docs = await page.evaluate(() => fetch('/api/documents').then((r) => r.json()));
const smoke = docs.find((doc) => doc.title === 'Smoke test');
if (!smoke || !smoke.finished_at) fail('finished state was not saved');
await page.evaluate((id) => fetch(`/api/documents/${id}`, { method: 'DELETE' }), smoke ? smoke.id : '');
await browser.close();

if (problems.length) {
  console.error(problems.join('\n'));
  process.exit(1);
}
log('ok');
