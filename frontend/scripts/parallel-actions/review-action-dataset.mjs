// Independent blind second review for the action-classifier dataset
// (ACTION-DATASET-20261111.md, 03 lane).  This is a review tool, not a product
// module and not a runner: it never starts a model, never touches the product
// tree and never edits a row.
//
// The order matters and is enforced by the tool, not by memory:
//
//   1. packet-check  the packet carries X, candidate Y, criterion and source;
//                    it must NOT carry 01's verdicts. Refuses if it does.
//   2. sample        deterministic 10% pick (seed = sha256 of the packet), so
//                    neither 01 nor 03 can choose which rows get reviewed.
//   3. render        prints only the sampled rows for my judgement.
//   4. seal          every sampled row needs one pass/fail + one-sentence
//                    reason; the sealed file's sha256 is written out before
//                    any 01 label can be read.
//   5. unblind       refuses without a matching seal, then reports raw
//                    agreement, class distribution and skip / non-skip splits.
//
// Usage
//   node scripts/parallel-actions/review-action-dataset.mjs packet-check --packet <file>
//   node scripts/parallel-actions/review-action-dataset.mjs render --packet <file>
//   node scripts/parallel-actions/review-action-dataset.mjs seal --packet <file> --verdicts <jsonl> --out <sealed.json>
//   node scripts/parallel-actions/review-action-dataset.mjs unblind --packet <file> --sealed <file> --labels <01 labels> [--out <agreement.json>]
//   node scripts/parallel-actions/review-action-dataset.mjs --self-test
import { createHash } from 'node:crypto';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const CRITERION_SHA256 = '56092d0c6e5ba0a03e8dc4096e3edb1bb2e4123b351b9f14d6884afdea11d21c';
const SAMPLE_RATE = 0.10;
const AGREEMENT_FLOOR = 0.85;

/** Keys that would break the blind: 01's verdicts, reasons or review notes. */
const FORBIDDEN_ROW_KEYS = new Set([
  'verdict', 'verdicts', 'pass', 'passed', 'ok', 'label', 'label01',
  'review', 'review01', 'reviewer', 'reviewedat', 'reviewreason', 'issues',
  'passfail', 'judgement01', 'reason01', 'decision01',
]);

const VOCAB_URL = new URL('../../../../../results/action-dataset-20261111/labels-v1.json', import.meta.url);

/** The 115 fine-grained predicates and their coarse groups, from 01's frozen
 * vocabulary file. Reading it is not reading 01's verdicts. */
function loadVocabulary() {
  const text = readFileSync(VOCAB_URL, 'utf8');
  const data = JSON.parse(text);
  const actionToGroup = new Map();
  for (const group of data.groups ?? []) {
    for (const predicate of group.predicates ?? []) {
      if (actionToGroup.has(predicate)) throw new Error(`predicate ${predicate} appears in two groups`);
      actionToGroup.set(predicate, group.group);
    }
  }
  if (actionToGroup.size !== 115) throw new Error(`vocabulary has ${actionToGroup.size} predicates, expected 115`);
  return { actionToGroup, sha256: sha256(text) };
}

const sha256 = (text) => createHash('sha256').update(text, 'utf8').digest('hex');
const canonical = (value) => JSON.stringify(value, Object.keys(value ?? {}).sort());

function rowsOf(packet) {
  if (Array.isArray(packet)) return packet;
  if (Array.isArray(packet.rows)) return packet.rows;
  throw new Error('packet must be an array of rows or {rows:[...]}');
}

function stableRowId(row, index) {
  const id = row.rowId ?? row.id;
  if (typeof id !== 'string' || !id.trim()) throw new Error(`row ${index} has no rowId`);
  return id;
}

/** Steps as the row carries them: 0/1/2 entries of {action, object}. */
function stepsOf(row) {
  const steps = row.y?.steps ?? row.y;
  if (!Array.isArray(steps)) throw new Error(`row ${row.rowId} y.steps is not an array`);
  if (steps.length > 2) throw new Error(`row ${row.rowId} has ${steps.length} steps (max 2)`);
  for (const step of steps) {
    if (typeof step?.action !== 'string' || !step.action) {
      throw new Error(`row ${row.rowId} step.action is not a fine-grained predicate`);
    }
  }
  return steps;
}

function classOf(row) {
  const steps = stepsOf(row);
  return steps.length === 0 ? 'skip' : steps.length === 1 ? '1step' : '2step';
}

/** Blinding and provenance gates shared by every command. */
export function checkPacket(packet, vocabulary = null) {
  const rows = rowsOf(packet);
  const vocab = vocabulary ?? loadVocabulary();
  const problems = [];
  if (!rows.length) problems.push('packet has no rows');
  if (packet?.criterionSha256 && packet.criterionSha256 !== CRITERION_SHA256) {
    problems.push(`criterion sha256 ${packet.criterionSha256} is not the frozen ${CRITERION_SHA256}`);
  }
  const seen = new Set();
  rows.forEach((row, index) => {
    const id = stableRowId(row, index);
    if (seen.has(id)) problems.push(`duplicate rowId ${id}`);
    seen.add(id);
    const badKeys = Object.keys(row).filter((key) => FORBIDDEN_ROW_KEYS.has(key.toLowerCase())
      || /^01/i.test(key) || /^review/i.test(key));
    if (badKeys.length) problems.push(`row ${id} carries 01-side fields (${badKeys.join(',')}): not blind`);
    for (const field of ['source', 'worldId', 'characterId', 'x', 'yRationale', 'labelSource']) {
      if (row[field] == null) problems.push(`row ${id} is missing ${field}`);
    }
    // 03 may not review rows it produced or first-labelled.
    for (const field of ['generatedBy', 'constructedBy', 'firstLabeller', 'annotator']) {
      if (typeof row[field] === 'string' && /03|actions/i.test(row[field])) {
        problems.push(`row ${id} was generated/first-labelled by 03 (${field}=${row[field]})`);
      }
    }
    let steps = [];
    try {
      steps = stepsOf(row);
    } catch (error) {
      problems.push(error.message);
    }
    for (const step of steps) {
      const group = vocab.actionToGroup.get(step.action);
      if (!group) problems.push(`row ${id} step.action ${step.action} is not one of the 115 predicates`);
      else if (steps.length && row.yGroup != null) {
        const declared = Array.isArray(row.yGroup) ? row.yGroup : [row.yGroup];
        if (!declared.includes(group) && !declared.some((entry) => String(entry).includes(group))) {
          problems.push(`row ${id} yGroup ${JSON.stringify(row.yGroup)} does not contain the first step's group ${group}`);
        }
      }
    }
    if (packet?.vocabularySha256 && packet.vocabularySha256 !== vocab.sha256) {
      problems.push(`packet vocabularySha256 ${packet.vocabularySha256} is not the frozen ${vocab.sha256}`);
    }
    const ids = new Set((row.x?.candidates ?? []).map((candidate) => candidate?.id ?? candidate));
    for (const step of Array.isArray(row.y?.steps ?? row.y) ? (row.y?.steps ?? row.y) : []) {
      if (step?.object != null && !ids.has(step.object)) {
        problems.push(`row ${id} step.object ${step.object} is not a candidate id`);
      }
    }
    if (typeof row.yRationale !== 'string' || !row.yRationale.trim()) {
      problems.push(`row ${id} has no yRationale`);
    }
  });
  return { rows, problems };
}

/** Deterministic 10% sample: sort by sha256(seed + rowId), take the first k. */
export function sampleRows(packetSha256, rowIds) {
  const ordered = [...rowIds].sort((a, b) => {
    const ha = sha256(`${packetSha256}:${a}`);
    const hb = sha256(`${packetSha256}:${b}`);
    return ha < hb ? -1 : ha > hb ? 1 : a < b ? -1 : a > b ? 1 : 0;
  });
  const k = Math.max(1, Math.ceil(rowIds.length * SAMPLE_RATE));
  return { sampled: ordered.slice(0, k), k, n: rowIds.length, seed: packetSha256 };
}

function readJson(file) {
  return JSON.parse(readFileSync(file, 'utf8'));
}

function readVerdicts(file) {
  const text = readFileSync(file, 'utf8');
  const rows = file.endsWith('.jsonl')
    ? text.split(/\r?\n/).filter((line) => line.trim()).map((line) => JSON.parse(line))
    : JSON.parse(text).verdicts ?? JSON.parse(text);
  if (!Array.isArray(rows)) throw new Error('verdicts file must be JSONL rows or {verdicts:[...]}');
  const byRow = new Map();
  for (const row of rows) {
    const id = row.rowId ?? row.id;
    if (!id) throw new Error('verdict without rowId');
    if (byRow.has(id)) throw new Error(`two verdicts for ${id}`);
    const verdict = String(row.verdict ?? '').toLowerCase();
    if (verdict !== 'pass' && verdict !== 'fail') throw new Error(`verdict for ${id} must be pass|fail`);
    const reason = String(row.reason ?? '').trim();
    if (!reason) throw new Error(`verdict for ${id} has no reason`);
    byRow.set(id, {
      verdict, reason,
      ambiguity: Boolean(row.ambiguity),
      mySteps: Array.isArray(row.mySteps) ? row.mySteps : null,
    });
  }
  return byRow;
}

function cmdPacketCheck(file) {
  const text = readFileSync(file, 'utf8');
  const packet = JSON.parse(text);
  const { rows, problems } = checkPacket(packet);
  const ids = rows.map((row, index) => stableRowId(row, index));
  const { sampled, k, n } = sampleRows(sha256(text), ids);
  const classes = rows.reduce((acc, row) => {
    const key = classOf(row);
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  console.log(JSON.stringify({
    packet: file, packetSha256: sha256(text), rows: n,
    criterionSha256: packet?.criterionSha256 ?? null,
    classes, sampledCount: k, sampled,
    status: problems.length ? 'REJECTED' : 'ACCEPTED',
    problems,
  }, null, 2));
  return problems.length ? 1 : 0;
}

function cmdRender(file) {
  const text = readFileSync(file, 'utf8');
  const packet = JSON.parse(text);
  const vocab = loadVocabulary();
  const { rows, problems } = checkPacket(packet, vocab);
  if (problems.length) throw new Error(`packet rejected: ${problems.join('; ')}`);
  const ids = rows.map((row, index) => stableRowId(row, index));
  const { sampled } = sampleRows(sha256(text), ids);
  const byId = new Map(rows.map((row, index) => [stableRowId(row, index), row]));
  const blocks = sampled.map((id, index) => {
    const row = byId.get(id);
    const x = row.x ?? {};
    const steps = stepsOf(row);
    return [
      `### ${index + 1}/${sampled.length}  rowId=${id}`,
      `source=${row.source} world=${row.worldId} character=${row.characterId} labelSource=${row.labelSource}`,
      `X.character=${x.character ?? ''}  sanity=${x.sanity ?? ''}  personality=${(x.personality ?? []).join('/')}`,
      `X.goal=${x.goal ?? ''}`,
      `X.location=${x.location ?? ''}  present=${(x.present ?? []).map((p) => p?.name ?? p).join('、') || '（无）'}`,
      `X.items=${(x.items ?? []).map((p) => p?.name ?? p).join('、') || '（无）'}`,
      `X.justHappened=${x.justHappened ?? x.recent ?? ''}`,
      `X.candidates=${(x.candidates ?? []).map((c) => `${c?.id}(${c?.name ?? ''})`).join('、') || '（无）'}`,
      `Y.steps=${JSON.stringify(steps)}`,
      `Y.group=${JSON.stringify(row.yGroup ?? null)}  firstStepGroup=${steps.length ? (loadVocabulary().actionToGroup.get(steps[0].action) ?? '?') : 'skip'}  Y.rationale=${row.yRationale}`,
      row.skipReason ? `Y.skipReason=${row.skipReason}` : null,
      '',
    ].filter(Boolean).join('\n');
  });
  console.log(`criterion (frozen sha256 ${CRITERION_SHA256}):\n${readFileSync(new URL('../../../../../results/action-dataset-20261111/criterion.txt', import.meta.url), 'utf8').trim()}\n`);
  console.log(blocks.join('\n'));
  return 0;
}

function cmdSeal(packetFile, verdictsFile, outFile) {
  const text = readFileSync(packetFile, 'utf8');
  const packet = JSON.parse(text);
  const vocab = loadVocabulary();
  const { rows, problems } = checkPacket(packet, vocab);
  if (problems.length) throw new Error(`packet rejected: ${problems.join('; ')}`);
  const ids = rows.map((row, index) => stableRowId(row, index));
  const packetSha256 = sha256(text);
  const { sampled } = sampleRows(packetSha256, ids);
  const verdicts = readVerdicts(verdictsFile);
  const missing = sampled.filter((id) => !verdicts.has(id));
  if (missing.length) throw new Error(`no sealed verdict for ${missing.length}/${sampled.length}: ${missing.slice(0, 5).join(',')}`);
  const extra = [...verdicts.keys()].filter((id) => !sampled.includes(id));
  const sealed = {
    lane: '03-actions', role: 'independent blind second reviewer',
    criterionSha256: CRITERION_SHA256,
    vocabularySha256: vocab.sha256,
    packet: packetFile, packetSha256,
    sampleSeed: packetSha256, sampleRate: SAMPLE_RATE,
    sampledCount: sampled.length, rowCount: ids.length,
    sealedAt: new Date().toISOString(),
    sawLabels: false,
    verdicts: sampled.map((id) => ({ rowId: id, ...verdicts.get(id) })),
    unsampledVerdictsIgnored: extra,
  };
  sealed.sealSha256 = sha256(canonical(sealed));
  writeFileSync(outFile, `${JSON.stringify(sealed, null, 2)}\n`, 'utf8');
  writeFileSync(`${outFile}.sha256`, `${sealed.sealSha256}  ${outFile}\n`, 'utf8');
  console.log(JSON.stringify({
    sealed: outFile, sealSha256: sealed.sealSha256, sampled: sealed.sampledCount,
    pass: sealed.verdicts.filter((row) => row.verdict === 'pass').length,
    fail: sealed.verdicts.filter((row) => row.verdict === 'fail').length,
    ambiguity: sealed.verdicts.filter((row) => row.ambiguity).length,
  }, null, 2));
  return 0;
}

/** 01's labels, in any of the shapes a reviewer file may use. Missing rows are
 * reported as missing, never guessed. */
function readLabels(file) {
  const data = readJson(file);
  const rows = Array.isArray(data) ? data : data.rows ?? data.verdicts ?? data.labels ?? [];
  const map = new Map();
  for (const row of rows) {
    const id = row.rowId ?? row.id;
    const value = row.verdict ?? row.pass ?? row.label ?? row.result;
    if (!id || value == null) continue;
    const verdict = value === true ? 'pass' : value === false ? 'fail'
      : /^pass|^ok|^yes/i.test(String(value)) ? 'pass'
        : /^fail|^no/i.test(String(value)) ? 'fail' : null;
    if (!verdict) continue;
    map.set(id, { verdict, reason: row.reason ?? row.rationale ?? null });
  }
  return map;
}

function cmdUnblind(packetFile, sealedFile, labelsFile, outFile) {
  const sealed = readJson(sealedFile);
  const text = readFileSync(packetFile, 'utf8');
  const packetSha256 = sha256(text);
  if (sealed.packetSha256 !== packetSha256) throw new Error('sealed file belongs to another packet version');
  if (sealed.criterionSha256 !== CRITERION_SHA256) throw new Error('sealed file used a different criterion');
  const { sealSha256, ...rest } = sealed;
  const actual = sha256(canonical(rest));
  const packet = JSON.parse(text);
  const vocab = loadVocabulary();
  const { rows } = checkPacket(packet, vocab);
  const byId = new Map(rows.map((row, index) => [stableRowId(row, index), row]));
  const labels = readLabels(labelsFile);
  const compared = sealed.verdicts.filter((row) => labels.has(row.rowId));
  const missing = sealed.verdicts.filter((row) => !labels.has(row.rowId)).map((row) => row.rowId);
  const agree = compared.filter((row) => labels.get(row.rowId).verdict === row.verdict);
  const disagreements = compared.filter((row) => labels.get(row.rowId).verdict !== row.verdict)
    .map((row) => ({
      rowId: row.rowId, mine: row.verdict, mineReason: row.reason,
      theirs: labels.get(row.rowId).verdict, theirsReason: labels.get(row.rowId).reason,
      ambiguity: Boolean(row.ambiguity), class: classOf(byId.get(row.rowId)),
      y: byId.get(row.rowId).y,
    }));
  const byClass = (cls) => {
    const subset = compared.filter((row) => classOf(byId.get(row.rowId)) === cls);
    const same = subset.filter((row) => labels.get(row.rowId).verdict === row.verdict);
    return { n: subset.length, agree: same.length, rate: subset.length ? same.length / subset.length : null };
  };
  const distribution = compared.reduce((acc, row) => {
    const key = classOf(byId.get(row.rowId));
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  const report = {
    lane: '03-actions', role: 'independent blind second reviewer',
    criterionSha256: CRITERION_SHA256,
    packetSha256, sealSha256: sealed.sealSha256, sealVerified: actual === sealSha256,
    sealedAt: sealed.sealedAt, unblindedAt: new Date().toISOString(),
    labelsFile,
    sampled: sealed.verdicts.length, compared: compared.length, missingTheirLabels: missing,
    rawAgreement: compared.length ? agree.length / compared.length : null,
    confusion: {
      bothPass: compared.filter((row) => row.verdict === 'pass' && labels.get(row.rowId).verdict === 'pass').length,
      minePassTheirsFail: compared.filter((row) => row.verdict === 'pass' && labels.get(row.rowId).verdict === 'fail').length,
      mineFailTheirsPass: compared.filter((row) => row.verdict === 'fail' && labels.get(row.rowId).verdict === 'pass').length,
      bothFail: compared.filter((row) => row.verdict === 'fail' && labels.get(row.rowId).verdict === 'fail').length,
    },
    classDistribution: distribution,
    byClass: { skip: byClass('skip'), oneStep: byClass('1step'), twoStep: byClass('2step') },
    ambiguitiesIFlagged: sealed.verdicts.filter((row) => row.ambiguity).map((row) => row.rowId),
    disagreements,
    agreementFloor: AGREEMENT_FLOOR,
    verdict: compared.length && agree.length / compared.length >= AGREEMENT_FLOOR
      ? 'AGREEMENT_AT_OR_ABOVE_FLOOR (does not prove the labels are correct)'
      : 'AGREEMENT_BELOW_FLOOR: report the disagreements first, do not silently edit the criterion',
  };
  const json = `${JSON.stringify(report, null, 2)}\n`;
  if (outFile) writeFileSync(outFile, json, 'utf8');
  console.log(json);
  return 0;
}

function selfTest() {
  const NL = String.fromCharCode(10);
  const criterion = readFileSync(new URL('../../../../../results/action-dataset-20261111/criterion.txt', import.meta.url), 'utf8');
  if (sha256(criterion) !== CRITERION_SHA256) throw new Error('criterion file hash drifted');

  const row = (id, steps, extra = {}) => ({
    rowId: id, source: 'constructed', worldId: 'w1', characterId: 'c1', labelSource: 'construct',
    x: { character: '甲', goal: '到钟楼', location: '巷口', present: [], items: [],
      justHappened: '无', sanity: 50, personality: [], candidates: [{ id: 'door', name: '门' }] },
    y: { steps }, yGroup: steps.length ? ['移动'] : [], yRationale: '去钟楼要先出门', ...extra,
  });

  // 1. Schema, classes and every rejection gate.
  const good = { criterionSha256: CRITERION_SHA256, rows: [row('r1', []), row('r2', [{ action: '移动', object: null }])] };
  const checked = checkPacket(good);
  if (checked.problems.length) throw new Error(`valid packet rejected: ${checked.problems.join('; ')}`);
  if (classOf({ rowId: 'x', y: { steps: [] } }) !== 'skip') throw new Error('skip class wrong');
  if (classOf({ rowId: 'x', y: { steps: [{ action: '移动' }, { action: '观察' }] } }) !== '2step') throw new Error('2step class wrong');
  const expectProblem = (packet, fragment, label) => {
    if (!checkPacket(packet).problems.some((problem) => problem.includes(fragment))) {
      throw new Error(`${label} not caught`);
    }
  };
  expectProblem({ criterionSha256: CRITERION_SHA256, rows: [row('r1', [], { verdict: 'pass' })] }, 'not blind', 'verdict leak');
  expectProblem({ criterionSha256: CRITERION_SHA256, rows: [row('r1', [], { reviewNote: 'ok' })] }, 'not blind', 'review field leak');
  expectProblem({ criterionSha256: CRITERION_SHA256, rows: [row('r1', [], { generatedBy: '03-actions' })] }, 'generated/first-labelled', 'own row');
  expectProblem({ criterionSha256: 'deadbeef', rows: [row('r1', [])] }, 'not the frozen', 'criterion drift');
  expectProblem({ criterionSha256: CRITERION_SHA256, rows: [row('r1', [{ action: '观察', object: 'nope' }])] }, 'not a candidate id', 'unknown object');
  expectProblem({ criterionSha256: CRITERION_SHA256, rows: [row('r1', [{ action: '飞升', object: null }])] }, 'not one of the 115', 'predicate outside the vocabulary');
  expectProblem({ criterionSha256: CRITERION_SHA256, rows: [row('r1', [{ action: '移动', object: null }], { yGroup: ['战斗'] })] }, 'does not contain the first step', 'yGroup mismatch');
  expectProblem({ criterionSha256: CRITERION_SHA256, rows: [row('r1', [{ action: '移动', object: null }])], vocabularySha256: 'deadbeef' }, 'vocabularySha256', 'vocabulary drift');

  // 2. Sampling is exactly 10% and deterministic per packet.
  const ids = Array.from({ length: 30 }, (_, index) => `r${index}`);
  const a = sampleRows('abc', ids);
  const b = sampleRows('abc', ids);
  if (a.k !== 3 || JSON.stringify(a.sampled) !== JSON.stringify(b.sampled)) throw new Error('sampling not deterministic 10%');
  if (JSON.stringify(sampleRows('abd', ids).sampled) === JSON.stringify(a.sampled)) throw new Error('sampling ignores the packet seed');

  // 3. Seal refuses a partial verdict set, accepts a complete one, hashes its content.
  const dir = mkdtempSync(join(tmpdir(), 'action-review-'));
  const at = (name) => join(dir, name);
  try {
    const rows = Array.from({ length: 40 }, (_, index) => row(`s${index}`, index % 3 === 0 ? [] : [{ action: '移动', object: null }]));
    const packet = { criterionSha256: CRITERION_SHA256, rows };
    writeFileSync(at('packet.json'), JSON.stringify(packet, null, 2));
    const packetText = readFileSync(at('packet.json'), 'utf8');
    const { sampled } = sampleRows(sha256(packetText), rows.map((entry) => entry.rowId));
    if (sampled.length !== 4) throw new Error(`40 rows must sample 4, got ${sampled.length}`);
    writeFileSync(at('partial.jsonl'), `${JSON.stringify({ rowId: sampled[0], verdict: 'pass', reason: 'ok' })}
`);
    let refused = false;
    try {
      cmdSeal(at('packet.json'), at('partial.jsonl'), at('sealed-bad.json'));
    } catch {
      refused = true;
    }
    if (!refused) throw new Error('seal accepted a partial verdict set');
    writeFileSync(at('verdicts.jsonl'), sampled.map((id) => JSON.stringify({ rowId: id, verdict: 'pass', reason: '符合判据' })).join(NL));
    capture(() => cmdSeal(at('packet.json'), at('verdicts.jsonl'), at('sealed.json')));
    const sealedObj = readJson(at('sealed.json'));
    if (sealedObj.sampledCount !== sampled.length) throw new Error('seal did not cover the sample');
    if (sealedObj.packetSha256 !== sha256(packetText)) throw new Error('seal did not pin the packet');

    // 4. Agreement math and the no-seal gate.
    writeFileSync(at('labels.json'), JSON.stringify({ rows: sampled.map((id, index) => ({ rowId: id, verdict: index === 1 ? 'fail' : 'pass' })) }));
    const report = JSON.parse(capture(() => cmdUnblind(at('packet.json'), at('sealed.json'), at('labels.json'), null)));
    if (Math.abs(report.rawAgreement - 0.75) > 1e-9) throw new Error(`agreement ${report.rawAgreement} != 0.75`);
    if (report.confusion.minePassTheirsFail !== 1) throw new Error('confusion matrix wrong');
    if (!report.sealVerified) throw new Error('seal hash not verified');
    if (!/BELOW_FLOOR/.test(report.verdict)) throw new Error('0.75 must be reported as below the 0.85 floor');
    // Above the floor the wording still must not claim the labels are correct.
    writeFileSync(at('labels-all.json'), JSON.stringify({ rows: sampled.map((id) => ({ rowId: id, verdict: 'pass' })) }));
    const high = JSON.parse(capture(() => cmdUnblind(at('packet.json'), at('sealed.json'), at('labels-all.json'), null)));
    if (high.rawAgreement !== 1) throw new Error('agreement 1.0 expected');
    if (!high.verdict.includes('does not prove')) throw new Error('agreement must not be presented as correctness proof');
    let noSeal = false;
    try {
      cmdUnblind(at('packet.json'), at('missing.json'), at('labels.json'), null);
    } catch {
      noSeal = true;
    }
    if (!noSeal) throw new Error('unblind ran without a seal');
    // A seal from another packet version is refused.
    writeFileSync(at('packet2.json'), JSON.stringify({ ...packet, note: 'v2' }));
    let wrongPacket = false;
    try {
      cmdUnblind(at('packet2.json'), at('sealed.json'), at('labels.json'), null);
    } catch {
      wrongPacket = true;
    }
    if (!wrongPacket) throw new Error('seal from another packet version was accepted');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
  console.log('self-test passed: blinding gate, provenance gate, deterministic 10% sample, complete-verdict seal, agreement math, no seal / wrong packet refused');
}

function capture(fn) {
  const original = console.log;
  let out = '';
  console.log = (...args) => { out += args.join(' '); };
  try {
    fn();
  } finally {
    console.log = original;
  }
  return out;
}

const [, , command, ...rest] = process.argv;
const flag = (name) => {
  const index = rest.indexOf(`--${name}`);
  return index >= 0 ? rest[index + 1] : undefined;
};

try {
  if (command === '--self-test') selfTest();
  else if (command === 'packet-check') process.exitCode = cmdPacketCheck(flag('packet'));
  else if (command === 'render') process.exitCode = cmdRender(flag('packet'));
  else if (command === 'seal') process.exitCode = cmdSeal(flag('packet'), flag('verdicts'), flag('out'));
  else if (command === 'unblind') process.exitCode = cmdUnblind(flag('packet'), flag('sealed'), flag('labels'), flag('out'));
  else {
    console.error('usage: packet-check|render|seal|unblind --packet <file> ... (or --self-test)');
    process.exitCode = 2;
  }
} catch (error) {
  console.error(`error: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
}
