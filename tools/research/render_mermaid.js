// Render Mermaid .mmd files to PNG using local puppeteer + Edge
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');

const DIAGRAMS_DIR = path.join(__dirname, 'diagrams');
const DIAGRAMS = [
  'fig3_1_system_architecture',
  'fig3_2_memory_architecture',
  'fig3_3_agent_pipeline',
  'fig3_4_campaign_fsm',
  'fig3_5_turn_dataflow',
];

const HTML_TEMPLATE = (mermaidCode) => `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <script>
    mermaid.initialize({ startOnLoad: true, theme: 'neutral', securityLevel: 'loose' });
  </script>
  <style>
    body { margin: 20px; background: white; }
    .mermaid { display: flex; justify-content: center; }
  </style>
</head>
<body>
  <div class="mermaid">
${mermaidCode}
  </div>
</body>
</html>`;

async function renderDiagram(mmName) {
  const mmdPath = path.join(DIAGRAMS_DIR, mmName + '.mmd');
  const pngPath = path.join(DIAGRAMS_DIR, mmName + '.png');
  const htmlPath = path.join(DIAGRAMS_DIR, mmName + '.html');

  const mermaidCode = fs.readFileSync(mmdPath, 'utf-8');
  console.log(`  Rendering: ${mmName}.mmd (${mermaidCode.length} chars)`);

  // Write HTML file
  const html = HTML_TEMPLATE(mermaidCode);
  fs.writeFileSync(htmlPath, html, 'utf-8');

  // Launch browser
  const browser = await puppeteer.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1600, height: 100, deviceScaleFactor: 2 });

    await page.goto('file:///' + htmlPath.replace(/\\/g, '/'), {
      waitUntil: 'networkidle0',
      timeout: 30000,
    });

    // Wait for mermaid to render
    await page.waitForSelector('.mermaid svg', { timeout: 15000 });

    // Get the SVG element's bounding box
    const boundingBox = await page.evaluate(() => {
      const svg = document.querySelector('.mermaid svg');
      if (!svg) return null;
      // Get the actual rendered size
      const box = svg.getBoundingClientRect();
      return { width: Math.ceil(box.width), height: Math.ceil(box.height + 10) };
    });

    if (!boundingBox) {
      throw new Error('Could not find rendered SVG');
    }

    await page.setViewport({
      width: Math.max(boundingBox.width + 40, 800),
      height: Math.max(boundingBox.height + 40, 200),
      deviceScaleFactor: 2,
    });

    const svgElement = await page.$('.mermaid svg');
    await svgElement.screenshot({ path: pngPath });

    const stats = fs.statSync(pngPath);
    console.log(`    OK: ${(stats.size / 1024).toFixed(1)} KB → ${mmName}.png`);
  } finally {
    await browser.close();
    // Clean up HTML
    try { fs.unlinkSync(htmlPath); } catch (e) { /* ignore */ }
  }
}

async function main() {
  console.log('='.repeat(50));
  console.log('Rendering Mermaid Diagrams with Edge + Puppeteer');
  console.log('='.repeat(50));

  for (const name of DIAGRAMS) {
    console.log('');
    try {
      await renderDiagram(name);
    } catch (err) {
      console.log(`    ERROR: ${err.message}`);
    }
  }

  console.log(`\n${'='.repeat(50)}`);
  console.log('Done.');
  console.log(`${'='.repeat(50)}`);
}

main().catch(console.error);
