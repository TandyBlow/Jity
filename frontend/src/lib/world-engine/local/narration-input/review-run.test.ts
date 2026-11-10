/** Dev-only: build the checker row for one 09 product run from the real
 * settled state, so the independent review judges the prose against the
 * actual state instead of the static q3 fixture. Skips unless REVIEW_EVIDENCE
 * points at a 09 evidence file. Not part of the normal suite. */
import { readFileSync, writeFileSync } from 'node:fs';
import { describe, it } from 'vitest';
import type { WorldState } from '../../types';
import { projectNarrationInput } from './project';
import { renderLegacyInput } from './render-legacy';
import { parseLegacyInput } from '../narration-quality/parse-legacy';
import { reviewNarration } from '../narration-quality/review';
import { genderOptions } from '../narration-quality/genders';

const evidencePath = process.env.REVIEW_EVIDENCE;
const outPath = process.env.REVIEW_OUT;

function buildBefore(after: WorldState): WorldState {
  const initial = after.initial;
  const characters = Object.fromEntries(Object.entries(initial.characters).map(([id, character]) => [
    id,
    {
      id,
      position: character.initialPosition,
      appearanceChanges: [],
      personalityChanges: [],
      sanity: character.initialSanity,
      tasks: Object.fromEntries(Object.entries(character.tasks ?? {}).map(([taskId, task]) => [taskId, { ...task }])),
    },
  ]));
  return { ...after, time: initial.initialTime, characters };
}

describe.skipIf(!evidencePath)('09 state review', () => {
  it('builds the real-state row and reviews the shown text', () => {
    const evidence = JSON.parse(readFileSync(evidencePath as string, 'utf8'));
    const turn = evidence.turns[0];
    const final = turn.snapshotAfterTurn.transport.state as WorldState;
    const narrations = turn.snapshotAfterTurn.transport.narrations;
    const rootText = narrations['point_root_world_dragon_raja_free_day'].text;
    const pointAfter = { ...final, time: { ...final.time, dateTime: '2009-10-17T15:21:00' } };
    const auto1After = { ...final, time: { ...final.time, dateTime: '2009-10-17T15:22:00' } };
    const auto2After = final;
    const rowFor = (id: string, before: WorldState, after: WorldState, delta: Record<string, unknown>, text: string) => {
      const timeAdvance = { boundary: 'elapsed' as const, duration: { amount: 1, unit: 'minute' as const } };
      const projected = projectNarrationInput({ before, after, delta: delta as never, timeAdvance, viewpointId: after.protagonistId });
      const legacy = renderLegacyInput(projected.projection);
      const input = parseLegacyInput(legacy);
      if (!input) throw new Error('legacy input did not round-trip');
      const report = reviewNarration({ id, input, text, options: { genders: genderOptions(), priorTexts: [rootText] } });
      return { id, input, report };
    };
    const beforePoint = buildBefore(final);
    const pointDelta = { lu: { entityId: 'lu', positionSet: final.characters.lu.position } };
    const rowPoint = rowFor('b7cd-point', beforePoint, pointAfter, pointDelta, narrations['point_round_3_1'].text);
    const beforeAuto1 = { ...pointAfter, time: { ...pointAfter.time, dateTime: '2009-10-17T15:21:00' } };
    const rowAuto1 = rowFor('b7cd-auto1', beforeAuto1, auto1After, {}, narrations['point_round_auto_mwb49dw4_1_1'].text);
    const beforeAuto2 = { ...auto1After, time: { ...auto1After.time, dateTime: '2009-10-17T15:22:00' } };
    const rowAuto2 = rowFor('b7cd-auto2', beforeAuto2, auto2After, {}, narrations['point_round_auto_mwb4avcm_2_1'].text);
    if (outPath) writeFileSync(outPath, `${JSON.stringify([rowPoint, rowAuto1, rowAuto2], null, 2)}
`);
    for (const row of [rowPoint, rowAuto1, rowAuto2]) {
      for (const finding of row.report.findings) {
        console.log(row.id, finding.severity, finding.kind, '|', finding.sentence.slice(0, 60), '|', finding.detail.slice(0, 80));
      }
      console.log(row.id, 'counts', row.report.counts);
    }
  }, 120_000);
});
