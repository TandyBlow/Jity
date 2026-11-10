/** Freeze the six-seed request set for one batch.
 *
 * This script does not generate anything. It validates the shared 01 package
 * hashes, loads only the model-visible fields, renders the exact chat user turn
 * with the product's own trained-input renderer, and writes:
 *
 *   data/<batch>/requests.jsonl  one line per (case, seed) call
 *   data/<batch>/expected.jsonl  input + required facts + licensed names for
 *                                the checker; the reference text is NEVER copied
 *   data/<batch>/plan.json       batch identity and every hash the runner needs
 *
 * Run from frontend/ so jiti resolves the product renderer:
 *   node_modules/.bin/jiti ../experiments/narration-best-of-n/src/prepare.ts --batch b01
 */
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderTrainedInstructUser, type TrainedSceneView } from '../../../frontend/src/lib/world-engine/local/narration-generation/trained-input';

const HERE = dirname(fileURLToPath(import.meta.url));
const EXPERIMENT = resolve(HERE, '..');
const FRONTEND = resolve(EXPERIMENT, '../../frontend');

const sha256 = (bytes: string | Buffer): string => createHash('sha256').update(bytes).digest('hex');

interface BatchConfig {
  batchId: string;
  caseIds: string[];
  seeds: number[];
  sharedPack: {
    root: string;
    manifestSha256: string;
    casesSha256: string;
    rubricSha256: string;
  };
  model: Record<string, unknown>;
  template: { kind: string; system: string; userRenderer: string; addGenerationPrompt: boolean };
  sampling: Record<string, unknown>;
  outputs: Record<string, string>;
}

interface PackCase {
  caseId: string;
  category: string;
  worldFamily: string;
  source?: Record<string, unknown>;
  viewpoint?: string;
  input: TrainedSceneView;
  requiredFacts?: unknown[];
  licensedEntities?: string[];
  priorTexts?: string[];
  notes?: string;
}

function argValue(name: string): string {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`missing_argument:${name}`);
  return process.argv[index + 1];
}

function loadJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, 'utf8')) as T;
}

function loadJsonl<T>(path: string): T[] {
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as T);
}

function assertHash(label: string, actual: string, expected: string): void {
  if (actual !== expected) throw new Error(`${label}_sha256_mismatch:${actual}!=${expected}`);
}

function main(): void {
  const batch = argValue('--batch');
  const configPath = join(EXPERIMENT, 'configs', `${batch}.json`);
  const config = loadJson<BatchConfig>(configPath);
  const packRoot = config.sharedPack.root;
  const manifestPath = join(packRoot, 'manifest.json');
  const casesPath = join(packRoot, 'cases.jsonl');
  const rubricPath = join(packRoot, 'RUBRIC.md');

  assertHash('manifest', sha256(readFileSync(manifestPath)), config.sharedPack.manifestSha256);
  assertHash('cases', sha256(readFileSync(casesPath)), config.sharedPack.casesSha256);
  if (existsSync(rubricPath)) assertHash('rubric', sha256(readFileSync(rubricPath)), config.sharedPack.rubricSha256);

  const manifest = loadJson<{
    package: string;
    caseCount: number;
    files: Record<string, string>;
    cases: Array<{ caseId: string; inputSha256: string; category: string }>;
  }>(manifestPath);
  assertHash('manifest_cases_field', manifest.files['cases.jsonl'], config.sharedPack.casesSha256);

  const rows = loadJsonl<PackCase>(casesPath);
  const byId = new Map(rows.map((row) => [row.caseId, row]));
  const manifestById = new Map(manifest.cases.map((row) => [row.caseId, row]));
  const cases: PackCase[] = [];
  for (const caseId of config.caseIds) {
    const row = byId.get(caseId);
    const manifestRow = manifestById.get(caseId);
    if (!row || !manifestRow) throw new Error(`case_missing:${caseId}`);
    if (manifestRow.inputSha256.length !== 64) throw new Error(`manifest_input_hash_invalid:${caseId}`);
    if (!row.input || !row.input['视角'] || !row.input['上回合状态'] || !row.input['本回合变化'] || !row.input['本回合状态']) {
      throw new Error(`case_input_shape_invalid:${caseId}`);
    }
    if (`${row.viewpoint ?? ''}` !== `${row.input['视角'] ?? ''}`) {
      throw new Error(`case_viewpoint_mismatch:${caseId}`);
    }
    cases.push(row);
  }

  const outDir = join(EXPERIMENT, 'data', batch);
  mkdirSync(outDir, { recursive: true });

  const requests: Array<Record<string, unknown>> = [];
  const expected: Array<Record<string, unknown>> = [];
  const planCases: Array<Record<string, unknown>> = [];
  for (const row of cases) {
    const userPrompt = renderTrainedInstructUser(row.input);
    const userPromptSha256 = sha256(userPrompt);
    const manifestRow = manifestById.get(row.caseId);
    expected.push({
      caseId: row.caseId,
      category: row.category,
      worldFamily: row.worldFamily,
      inputSha256: manifestRow?.inputSha256,
      input: row.input,
      requiredFacts: row.requiredFacts ?? [],
      licensedEntities: row.licensedEntities ?? [],
      priorTexts: row.priorTexts ?? [],
      viewpoint: row.viewpoint ?? row.input['视角'],
      notes: row.notes ?? '',
      authors: row.source ?? null,
    });
    planCases.push({
      caseId: row.caseId,
      category: row.category,
      inputSha256: manifestRow?.inputSha256,
      userPromptSha256,
      userPromptChars: [...userPrompt].length,
    });
    for (const seed of config.seeds) {
      requests.push({
        callId: `${row.caseId}:s${seed}`,
        caseId: row.caseId,
        seed,
        inputSha256: manifestRow?.inputSha256,
        system: config.template.system,
        userPrompt,
        userPromptSha256,
        template: config.template.kind,
        sampling: config.sampling,
      });
    }
  }

  const writeJsonl = (name: string, rowsToWrite: Array<Record<string, unknown>>): string => {
    const path = join(outDir, name);
    const text = rowsToWrite.map((row) => JSON.stringify(row)).join('\n') + '\n';
    writeFileSync(path, text, 'utf8');
    return sha256(text);
  };
  const requestsSha256 = writeJsonl('requests.jsonl', requests);
  const expectedSha256 = writeJsonl('expected.jsonl', expected);

  const plan = {
    batchId: config.batchId,
    preparedAt: new Date().toISOString(),
    pack: {
      package: manifest.package,
      caseCount: manifest.caseCount,
      manifestSha256: config.sharedPack.manifestSha256,
      casesSha256: config.sharedPack.casesSha256,
      rubricSha256: config.sharedPack.rubricSha256,
    },
    seeds: config.seeds,
    model: config.model,
    template: config.template,
    sampling: config.sampling,
    calls: requests.length,
    cases: planCases,
    requestsSha256,
    expectedSha256,
    renderer: 'frontend/src/lib/world-engine/local/narration-generation/trained-input.ts:renderTrainedInstructUser',
    referenceExcluded: true,
    frontendRoot: FRONTEND,
  };
  writeFileSync(join(outDir, 'plan.json'), `${JSON.stringify(plan, null, 2)}\n`, 'utf8');

  console.log(JSON.stringify({
    batch: config.batchId,
    cases: planCases,
    calls: requests.length,
    requestsSha256,
    expectedSha256,
    outDir,
  }, null, 2));
}

main();
