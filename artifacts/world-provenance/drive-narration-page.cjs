/**
 * Drive /narration in a real headless Edge and measure:
 *   click → fetch returns (transport)
 *   click → text painted (browser total)
 *   browser total − server total = remaining overhead
 *
 * Three passes: cold request, hot request, and a tiny-budget timeout run.
 */
const fs = require('node:fs');
const path = require('node:path');
const puppeteer = require(path.join(process.cwd(), 'node_modules', 'puppeteer'));

const PAGE = process.env.PAGE || 'http://127.0.0.1:3100/narration';

async function clickAndWait(page, budget, forceTimeout = '') {
  await page.evaluate((value) => {
    const input = document.querySelector('input[type="number"]');
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    if (input._valueTracker) input._valueTracker.setValue('');
    setter.call(input, String(value));
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }, budget);
  await page.evaluate((value) => {
    const input = document.querySelector('input[placeholder="f3"]');
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, 'value').set;
    // React 用内部 value tracker 去重，先清掉再写，事件才不会被吞
    if (input._valueTracker) input._valueTracker.setValue('');
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }, forceTimeout);
  await new Promise((resolve) => setTimeout(resolve, 150));
  await page.evaluate(() => {
    window.__started = performance.now();
  });
  const click = async () => {
    await page.evaluate(() => {
      const button = [...document.querySelectorAll('button')].find((item) =>
        item.textContent.includes('生成') || item.textContent.includes('处理中'));
      button.click();
    });
  };
  await click();
  // 进入处理中 → 回到可点击，才算这一轮真的结束
  await page.waitForFunction(() => document.body.innerText.includes('处理中'), { timeout: 20000 });
  await page.waitForFunction(() => !document.body.innerText.includes('处理中'), { timeout: 120000 });
  await page.evaluate(() => new Promise((resolve) =>
    requestAnimationFrame(() => requestAnimationFrame(resolve))));
  return page.evaluate(() => {
    const text = document.body.innerText;
    const pick = (label) => {
      const line = text.split('\n').find((item) => item.includes(label));
      return line ? line.trim() : null;
    };
    const editedBlock = text.split('编辑稿')[1] || '';
    return {
      browserMs: Math.round(performance.now() - window.__started),
      emptyState: editedBlock.includes('本回合未生成完整正文'),
      gaps: text.split(String.fromCharCode(10)).map((l) => l.trim())
        .filter((l) => l.startsWith('缺口：')),
      edited: (text.split('编辑稿')[1] || '').split('\n')[1] || '',
      status: pick('完成') || pick('未完成'),
      timing: pick('耗时：'),
      browser: pick('浏览器：'),
      remaining: pick('剩余开销'),
      repeat: pick('自动重复提示'),
    };
  });
}

async function main() {
  const browser = await puppeteer.launch({
    headless: 'new',
    executablePath: process.env.EDGE_PATH
      || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  await page.goto(PAGE, { waitUntil: 'networkidle0' });
  await page.waitForFunction(() => document.body.innerText.includes('生成'));

  const cold = await clickAndWait(page, 20);
  const hot = await clickAndWait(page, 20);
  const partial = await clickAndWait(page, 20, 'f3');
  const timeout = await clickAndWait(page, 0.05);
  const agent = await browser.userAgent();
  await browser.close();

  const output = { agent, page: PAGE, cold, hot, partial, timeout };
  fs.writeFileSync(path.join(process.cwd(), 'artifacts/world-provenance/narration-page.json'),
                   JSON.stringify(output, null, 2));
  console.log(JSON.stringify(output, null, 2));
}

main().catch((error) => { console.error('FAILED', error.message); process.exit(1); });
