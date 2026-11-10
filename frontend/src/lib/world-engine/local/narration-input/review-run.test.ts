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
  it('builds the real-state rows and reviews every narration', () => {
    const evidence = JSON.parse(readFileSync(evidencePath as string, 'utf8'));
    const turn = evidence.turns[0];
    const final = turn.snapshotAfterTurn.transport.state as WorldState;
    const narrations = turn.snapshotAfterTurn.transport.narrations;
    const keys = Object.keys(narrations);
    const rootKey = keys.find((key) => key.startsWith('point_root'))!;
    const pointKey = keys.find((key) => key.startsWith('point_round_3_1'))!;
    const autoKeys = keys.filter((key) => key.startsWith('point_round_auto'));
    const rootText = narrations[rootKey].text;
    const pointText = narrations[pointKey].text;
    const rowFor = (id: string, before: WorldState, after: WorldState, delta: Record<string, unknown>, text: string, priors: string[]) => {
      const timeAdvance = { boundary: 'elapsed' as const, duration: { amount: 1, unit: 'minute' as const } };
      const projected = projectNarrationInput({ before, after, delta: delta as never, timeAdvance, viewpointId: after.protagonistId });
      const legacy = renderLegacyInput(projected.projection);
      const input = parseLegacyInput(legacy);
      if (!input) throw new Error('legacy input did not round-trip');
      const report = reviewNarration({ id, input, text, options: { genders: genderOptions(), priorTexts: priors } });
      return { id, input, report };
    };
    const beforePoint = buildBefore(final);
    const pointDelta = { lu: { entityId: 'lu', positionSet: final.characters.lu.position } };
    const pointAfter = { ...final, time: { ...final.time, dateTime: '2009-10-17T15:21:00' } };
    const rows = [rowFor('point', beforePoint, pointAfter, pointDelta, pointText, [rootText])];
    let before = pointAfter;
    const priors = [rootText, pointText];
    for (const [index, key] of autoKeys.entries()) {
      const after = { ...final, time: { ...final.time, dateTime: `2009-10-17T15:2${2 + index}:00` } };
      rows.push(rowFor(`auto${index + 1}`, before, after, {}, narrations[key].text, [...priors]));
      before = after;
      priors.push(narrations[key].text);
    }
    if (outPath) writeFileSync(outPath, `${JSON.stringify(rows, null, 2)}
`);
    for (const row of rows) {
      for (const finding of row.report.findings) {
        console.log(row.id, finding.severity, finding.kind, '|', finding.sentence.slice(0, 60), '|', finding.detail.slice(0, 80));
      }
      console.log(row.id, 'counts', row.report.counts);
    }
  }, 120_000);
});
