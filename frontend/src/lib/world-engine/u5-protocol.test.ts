import { expect, test } from 'vitest';
import { validateRequest } from './protocol';
import intermediate from '../../../../design/world-protocol/v2/fixtures/branches/u5-preview.request.json';
import stageFixture from '../../../../design/world-protocol/v2/fixtures/api/checkpoint_stage_unit/request.json';
import scanFixture from '../../../../design/world-protocol/v2/fixtures/api/checkpoint_stage_time_scan/request.json';
import commitFixture from '../../../../design/world-protocol/v2/fixtures/api/commit_point/request.json';

test('real wire protocol accepts only explicit last U5 intermediate', () => {
  expect(() => validateRequest('preview_point', intermediate)).not.toThrow();
  const unmarked = structuredClone(intermediate);
  delete (unmarked.settlementGroups[0] as { previewStage?: string }).previewStage;
  expect(() => validateRequest('preview_point', unmarked)).toThrow(/pair/);
  expect(() => validateRequest('preview_point', { ...intermediate, settlementGroups: [intermediate.settlementGroups[0], intermediate.settlementGroups[0]] })).toThrow();
  expect(() => validateRequest('preview_point', { ...intermediate, settlementGroups: [{ ...intermediate.settlementGroups[0], previewStage: 'U4' }] })).toThrow();
});

test.each([true,false])('intermediate cannot stage/scan/commit (marker=%s)', marker => {
  const group = structuredClone(intermediate.settlementGroups[0]);
  if (!marker) delete (group as { previewStage?: string }).previewStage;
  expect(() => validateRequest('checkpoint_stage_unit', { ...stageFixture, candidates: group })).toThrow();
  expect(() => validateRequest('checkpoint_stage_time_scan', { ...scanFixture, candidates: { ...group, groupId: null, actorIds: [], positions: {}, appearances: {} } })).toThrow();
  expect(() => validateRequest('commit_point', { ...commitFixture, settlementGroups: [group] })).toThrow();
});

test('completed U6 validates as preview, stage and commit', () => {
  const group = { ...intermediate.settlementGroups[0], sanities: { person_c: 45 } };
  delete (group as { previewStage?: string }).previewStage;
  expect(() => validateRequest('preview_point', { ...intermediate, settlementGroups: [group] })).not.toThrow();
  expect(() => validateRequest('checkpoint_stage_unit', { ...stageFixture, candidates: group })).not.toThrow();
  expect(() => validateRequest('commit_point', { ...commitFixture, settlementGroups: [group] })).not.toThrow();
});

test('copying the intermediate point into a commit cannot bypass the group gate', () => {
  const request = { ...commitFixture, settlementGroups: [], point: { ...commitFixture.point,
    entityDeltas: { person_c: { entityId: 'person_c', personalityChanges: [{id:'pc',text:'更谨慎',supersedes:[]}] } } } };
  expect(() => validateRequest('commit_point', request)).toThrow(/pair/);
});
