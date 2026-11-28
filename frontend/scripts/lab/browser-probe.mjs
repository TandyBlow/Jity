// Browser-only baseline: launch headless Edge, hold about:blank, exit.
import { chromium } from 'playwright';
const seconds = Number(process.argv[2] ?? 20);
const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await (await browser.newContext()).newPage();
await page.goto('about:blank');
await new Promise((r) => setTimeout(r, seconds * 1000));
await browser.close();
