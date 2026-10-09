// Summarize CRF-vs-plain paired training rounds (user-directed CRF round).
//
// Input:  artifacts/benchmark/crf-compare-raw-<ts>.json (written by
//         train-span-crf-compare.py — per-case rows per seed x head x decode)
// Anchor: artifacts/benchmark/labeler-trial-1791516015611-spans.json
//         (frozen shipped model, fp32 arm — recomputed here, not trusted
//         from stdout)
// Output: artifacts/benchmark/crf-compare-<ts>.json + console report.
//
// The report keeps FOUR things side by side per the round's spec, so a
// boundary improvement cannot hide a hallucination increase:
//   per-field strict / whole-sentence (both-fields) strict /
//   empty-field false positives (with texts) / per-example flips
//   (CRF-Viterbi vs paired plain-greedy and plain-constrained).
//
// Usage: node scripts/summarize-crf.mjs <crf-compare-raw-*.json> [more-raw.json ...]
// 多个 raw 文件（如修流前后的分批结果）会被合并；同 (seed, head) 重复时
// 取后面的文件（后跑的覆盖先跑的）。

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const artifactsDir = path.join(frontendRoot, "..", "artifacts", "benchmark");

const log = (...parts) => console.log(...parts);

async function main() {
  const rawPaths = process.argv.slice(2);
  if (rawPaths.length === 0) {
    console.error("usage: node scripts/summarize-crf.mjs <crf-compare-raw-*.json> [more-raw.json ...]");
    process.exit(2);
  }
  const frozen = JSON.parse((await readFile(path.join(artifactsDir, "labeler-trial-1791516015611-spans.json"))).toString("utf-8"));
  const frozenCases = frozen.arms[1].cases; // fp32 arm

  // 多 raw 合并：同 (seed, head) 后跑的覆盖先跑的（修流后的 4711 覆盖旧臂）。
  // *legacyval* 文件只做锚点验证（逐位复现冻结模型的证据），不进主表——
  // 它的验证路径（train 态、Dropout 消耗 rng）与其余种子不同，混表会污染
  // 语义。
  const byKey = new Map();
  let legacyRaw = null;
  for (const p of rawPaths) {
    const raw = JSON.parse((await readFile(path.resolve(p))).toString("utf-8"));
    if (p.includes("legacyval")) {
      legacyRaw = raw;
      continue;
    }
    for (const r of raw.results) byKey.set(`${r.seed}|${r.head}`, r);
  }
  const results = [...byKey.values()];
  results.sort((a, b) => (a.seed === b.seed ? (a.head === "plain" ? -1 : 1) - (b.head === "plain" ? -1 : 1) : a.seed - b.seed));
  const seeds = [...new Set(results.map((r) => r.seed))];
  const decodeNames = [...new Set(results.flatMap((r) => Object.keys(r.rows[0].decodes)))];

  // ── 锚点重算：plain@4711 必须逐例等于冻结模型（fp32 臂，两种解码）。
  // 优先用 legacyval 原始（历史验证路径，可逐位复现）；否则用表内
  // plain@4711（现行为，冻结模型的验证路径已被 fd02a44 修正，逐位复现
  // 原则上不可达，只做分数级对照）。────────────────────────────────────
  const anchorSource = legacyRaw
    ? legacyRaw.results.find((r) => r.seed === 4711 && r.head === "plain")
    : results.find((r) => r.seed === 4711 && r.head === "plain");
  const anchor = anchorSource;
  const anchorDiffs = [];
  for (let i = 0; i < anchor.rows.length; i += 1) {
    for (const mode of ["greedy", "constrained"]) {
      if ([anchor.rows[i].decodes[mode].predItem, anchor.rows[i].decodes[mode].predTarget].join("|")
        !== [frozenCases[i][mode].predItem, frozenCases[i][mode].predTarget].join("|")) {
        anchorDiffs.push({ text: anchor.rows[i].text, mode });
      }
    }
  }
  const anchorVerdict = {
    source: legacyRaw ? "legacyval rerun (pre-fd02a44 validation semantics)" : "in-table plain@4711 (post-fix semantics, score-level only)",
    caseIdenticalToFrozen: anchorDiffs.length === 0,
    diffs: anchorDiffs,
  };

  // ── 速率表：每 seed × head × decode（解码集按臂各自取：plain 有
  // greedy+constrained，crf 有 viterbi）。───────────────────────────────
  const rate = (rows, mode, field) => `${rows.filter((r) => r.decodes[mode][`${field}Strict`]).length}/${rows.length}`;
  const both = (rows, mode) => `${rows.filter((r) => r.decodes[mode].itemStrict && r.decodes[mode].targetStrict).length}/${rows.length}`;
  const table = results.map((r) => {
    const modes = Object.keys(r.rows[0].decodes);
    return {
      seed: r.seed,
      head: r.head,
      merged: Object.fromEntries(modes.map((mode) => [mode, {
        itemStrict: rate(r.rows, mode, "item"),
        targetStrict: rate(r.rows, mode, "target"),
        bothFields: both(r.rows, mode),
      }])),
      byBatch: Object.fromEntries(["devClassic", "devGroups", "scored"].map((batch) => {
        const rows = r.rows.filter((row) => row.batch === batch);
        return [batch, Object.fromEntries(modes.map((mode) => [mode, both(rows, mode)]))];
      })),
      emptyFieldFalsePositives: Object.fromEntries(modes.map((mode) => {
        const fps = r.rows.flatMap((row) => row.decodes[mode].emptyFieldFalsePositives.map((fp) => ({ batch: row.batch, text: row.text, field: fp.field, pred: fp.pred })));
        const byField = {};
        for (const fp of fps) byField[fp.field] = (byField[fp.field] ?? 0) + 1;
        return [mode, { total: fps.length, byField, cases: fps }];
      })),
    };
  });

  // ── 配对逐例得失（同种子内 CRF vs plain 两种解码）。──────────────────
  const pairedFlips = {};
  for (const seed of seeds) {
    const plain = results.find((r) => r.seed === seed && r.head === "plain");
    const crf = results.find((r) => r.seed === seed && r.head === "crf");
    pairedFlips[seed] = Object.fromEntries(["greedy", "constrained"].map((mode) => {
      const gains = [];
      const losses = [];
      for (let i = 0; i < crf.rows.length; i += 1) {
        const was = plain.rows[i].decodes[mode].itemStrict && plain.rows[i].decodes[mode].targetStrict;
        const now = crf.rows[i].decodes.viterbi.itemStrict && crf.rows[i].decodes.viterbi.targetStrict;
        if (was === now) continue;
        (now ? gains : losses).push({
          batch: crf.rows[i].batch,
          group: crf.rows[i].group,
          text: crf.rows[i].text,
          expectItem: crf.rows[i].expectItem,
          expectTarget: crf.rows[i].expectTarget,
          plain: { predItem: plain.rows[i].decodes[mode].predItem, predTarget: plain.rows[i].decodes[mode].predTarget },
          crfViterbi: { predItem: crf.rows[i].decodes.viterbi.predItem, predTarget: crf.rows[i].decodes.viterbi.predTarget },
        });
      }
      return [mode, { gains, losses }];
    }));
  }

  // ── 跨种子稳定性。───────────────────────────────────────────────────
  const parse = (s) => parseInt(s.split("/")[0], 10);
  const stability = {};
  for (const head of ["plain", "crf"]) {
    const modes = head === "plain" ? ["greedy", "constrained"] : ["viterbi"];
    stability[head] = Object.fromEntries(modes.map((mode) => {
      const perSeed = results.filter((r) => r.head === head).map((r) => parse(both(r.rows, mode)));
      return [mode, { perSeedBothFields: perSeed, mean: (perSeed.reduce((a, b) => a + b, 0) / perSeed.length).toFixed(2), spread: Math.max(...perSeed) - Math.min(...perSeed) }];
    }));
  }

  for (const row of table) {
    log(`seed ${row.seed} ${row.head}: ` + Object.entries(row.merged).map(([m, v]) => `${m} item ${v.itemStrict} tgt ${v.targetStrict} both ${v.bothFields}`).join(" | "));
    for (const [mode, fp] of Object.entries(row.emptyFieldFalsePositives)) {
      log(`  empty-field FP ${mode}: ${fp.total} (${JSON.stringify(fp.byField)})${fp.cases.length ? " e.g. " + fp.cases.slice(0, 4).map((c) => `${c.field}=${c.pred}@${c.text}`).join("; ") : ""}`);
    }
  }
  log(`anchor plain@4711 vs frozen fp32: ${anchorDiffs.length === 0 ? "OK (case-identical, both decodes)" : `DRIFT ${anchorDiffs.length} case(s): ` + anchorDiffs.slice(0, 6).map((d) => `${d.text}[${d.mode}]`).join("; ")}`);
  for (const [seed, byMode] of Object.entries(pairedFlips)) {
    for (const [mode, { gains, losses }] of Object.entries(byMode)) {
      log(`seed ${seed} crf-viterbi vs plain-${mode}: +${gains.length}/-${losses.length}`);
      for (const g of gains) log(`  gain: ${g.text} gold=${g.expectItem ?? "∅"}/${g.expectTarget ?? "∅"} plain=${g.plain.predItem ?? "∅"}/${g.plain.predTarget ?? "∅"} -> crf=${g.crfViterbi.predItem ?? "∅"}/${g.crfViterbi.predTarget ?? "∅"}`);
      for (const l of losses) log(`  loss: ${l.text} gold=${l.expectItem ?? "∅"}/${l.expectTarget ?? "∅"} plain=${l.plain.predItem ?? "∅"}/${l.plain.predTarget ?? "∅"} -> crf=${l.crfViterbi.predItem ?? "∅"}/${l.crfViterbi.predTarget ?? "∅"}`);
    }
  }
  log(`stability: ${JSON.stringify(stability)}`);

  const outPath = path.join(artifactsDir, `crf-compare-${Date.now()}.json`);
  await writeFile(outPath, JSON.stringify({
    trainSeeds: seeds,
    protocol: {
      corpusSplitRules: "frozen (span-labeler-corpus.json, sha unchanged); split asserted identical in train-span-crf-compare.py before training",
      pretrainingStart: "artifacts/benchmark/minirbt-h256-snapshot",
      budget: "EPOCHS=30, BATCH=16, AdamW lr 3e-4 wd 0.01, CPU, identical to the shipped model's training",
      pairing: "same seed -> same head-init stream + same per-epoch batch order for plain and CRF arms; seed 4711 plain anchors the pipeline against the frozen model (fp32 arm)",
      decodes: "plain -> greedy + whole-sentence constrained (as shipped); CRF -> Viterbi",
      crf: "linear-chain CRF over the 5 tags, emissions from the BERT encoder, transitions/start/end learned, NLL loss, Viterbi decode",
      citation: "Lample et al. 2016, Neural Architectures for Named Entity Recognition, https://aclanthology.org/N16-1030",
    },
    anchor: anchorVerdict,
    table,
    pairedFlips,
    stability,
    arms: results,
    exportedAt: new Date().toISOString(),
  }, null, 2));
  log(`saved: ${outPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
