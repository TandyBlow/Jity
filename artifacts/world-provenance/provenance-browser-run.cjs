/**
 * The same two-point chain as provenance-chain.cjs, executed inside a real
 * headless browser page (Edge/Chromium) with the page's own fetch:
 *   point A (real change) → 2 s advance → point B (real change)
 *   → read both back with get_state → derive evidence refs → decide `before`.
 */
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require(path.join(process.cwd(), 'node_modules', 'puppeteer'));

const BASE = process.env.BASE || 'http://127.0.0.1:8017';
const FIXTURE = path.join(process.cwd(),
  'design/world-protocol/v2/fixtures/projections/normal.expected.json');

function chainSource() {
  const source = fs.readFileSync(path.join(__dirname, 'provenance-chain.cjs'), 'utf8');
  const body = source.slice(source.indexOf('const ROSTER'),
                            source.indexOf('module.exports'));
  return 'window.__chain = (async (fetcher, base, template) => {\n'
    + body
    + 'return chain(fetcher, base, template);\n});';
}

async function main() {
  const initial = JSON.parse(fs.readFileSync(FIXTURE, 'utf8')).initial;
  delete initial.worldId;

  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: process.env.EDGE_PATH
      || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') console.error('page:', message.text());
  });
  await page.goto(`${BASE}/docs`, { waitUntil: 'domcontentloaded' });
  await page.addScriptTag({ content: chainSource() });
  const result = await page.evaluate(
    async (base, template) => window.__chain(window.fetch.bind(window), base, template),
    BASE, initial);
  const agent = await browser.userAgent();
  await browser.close();

  const output = { agent, ...result };
  fs.writeFileSync(path.join(__dirname, 'provenance-browser.json'),
                   JSON.stringify(output, null, 2));
  console.log(JSON.stringify(output, null, 2));
}

main().catch((error) => { console.error('FAILED', error.message); process.exit(1); });
