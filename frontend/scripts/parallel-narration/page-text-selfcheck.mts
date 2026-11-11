/** Offline self-check of recorded page text: which of 02's sentence-level rules
 * fire on the text a real run produced. No inference, no new product call — this
 * only re-reads evidence already on disk. The four rule groups the user asked to
 * compare are the deterministic regressions in product-regressions.test.ts; this
 * script reports what those rules say about the samples that already exist.
 *
 *   npx tsx frontend/scripts/parallel-narration/page-text-selfcheck.mts
 */
import { readFileSync } from 'node:fs';
import { stateReportViolations } from '../../src/lib/world-engine/local/narration-generation/licensed-sense';

const files = [
  'results/product/evidence/09-product-03turn-35ad.json',
  'results/product/evidence/09-product-03turn-d531.json',
  'results/product/evidence/09-product-03turn-08f4.json',
  'results/product/evidence/09-constrained-beats-9623.json',
];
const PROMPT_ECHO = /(必须全部|输出格式|只输出正文|【正文】|JSON|方向必须|方向是从到|不必写进正文|时间背景|只可使用|不要写成成功)/u;
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '../../../../..') + '/'
for (const f of files) {
  const doc = JSON.parse(readFileSync(root + f, 'utf8'));
  const turns = doc.turns ?? [];
  console.log('==', f.split('/').pop(), 'head', doc.head ?? doc.productState?.gitHead);
  for (const t of turns) {
    const text = String(t.text ?? '').trim();
    if (!text || text === '…') { console.log('  turn', t.turn, '| empty/placeholder'); continue; }
    const reports = stateReportViolations(text);
    const echo = PROMPT_ECHO.exec(text);
    console.log('  turn', t.turn, '|', t.textSource, '|', [...text].length, 'chars |',
      'state_report', reports.length, '| echo', echo ? echo[0] : '-');
    for (const r of reports) console.log('     report:', r.sentence.slice(0, 60));
  }
}
