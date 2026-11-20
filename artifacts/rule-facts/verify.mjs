// Read-only evidence checks. No server, browser, model, or credentials needed.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../../', import.meta.url));
const bytes = (name) => readFileSync(new URL(name, import.meta.url));
const read = (name) => JSON.parse(bytes(name));
const sha = (value) => createHash('sha256').update(value).digest('hex');
const manifest = read('manifest.json');
for (const [file, digest] of Object.entries(manifest.files)) assert.equal(sha(bytes(file)), digest, file);
for (const profile of Object.values(manifest.sourceProfiles)) {
  for (const [path, entry] of Object.entries(profile.files)) {
    if (entry.archiveSnapshot) assert.equal(sha(bytes(entry.archiveSnapshot)), entry.recordedWorkingSha256);
    else {
      const blob = execFileSync('git', ['-c', `safe.directory=${root.replaceAll('\\', '/')}`, '-C', root,
        'show', `${manifest.implementationCommit}:${path}`]);
      assert.equal(sha(blob), entry.implementationGitBlobSha256, path);
    }
  }
}
const http = read('http.json');
const db = read('database-evidence.json');
const first = read('latency-first.json');
const final = read('latency.json');
const review = read('review.json');
const selection = read('polish-selection.json');
assert.equal(http.status, 'PASS_RULE_FACTS_HTTP');
assert.equal(http.rows.length, 10);
assert.equal(db.rows.length, 10);
assert.equal(db.successfulCommits, 10);
assert.equal(db.narrativeGenerations, 20);
for (const row of http.rows) {
  const persisted = db.rows.find((item) => item.id === row.id);
  assert.equal(row.status, 'PASS');
  assert.equal(row.saved.version, 1);
  assert.equal(persisted.committedRequestIds.length, 1);
  assert.equal(persisted.point.stateDigest, row.saved.stateDigest);
  assert.equal(persisted.savedNarration, row.narration.text);
  assert.equal(row.narration.packet.anchor.stateDigest, row.saved.stateDigest);
  assert.equal(row.duplicateConsumption.sameRequestReplayed, true);
  assert.equal(row.duplicateConsumption.versionAfterRepeat, 1);
  assert.ok(['phase_invalid', 'version_mismatch'].includes(row.duplicateConsumption.freshRequestRefusal));
  assert.equal(persisted.inputs[0].intentStatus, 'consumed');
  assert.equal(persisted.inputs[0].ended, 1);
  assert.ok(persisted.allocations.some((allocation) => allocation.id === row.saved.pointId && allocation.kind === 'point'));
  const numeric = ['numeric', 'numeric-recover', 'lost-commit-response'].includes(row.id);
  if (numeric) {
    const delta = row.saved.entityDeltas.person_c;
    assert.equal(delta.sanitySet, row.id === 'numeric-recover' ? 9 : 8);
    assert.equal(delta.tasksAchieved.length, 1);
    assert.equal(delta.personalityChanges.length, 1);
    assert.ok(persisted.allocations.some((allocation) => allocation.id === delta.personalityChanges[0].id && allocation.kind === 'change'));
    assert.equal(row.saved.state.characters.person_c.tasks[delta.tasksAchieved[0]].status, 'achieved');
  } else if (row.id === 'move') {
    assert.deepEqual(row.saved.entityDeltas, { person_c: { entityId: 'person_c', positionSet: { containerId: 'hall', slotId: null, relativeTo: null } } });
  } else assert.deepEqual(row.saved.entityDeltas, {});
}
const lost = http.rows.find((row) => row.id === 'lost-commit-response');
assert.equal(lost.commitExchanges, 2);
assert.equal(lost.lostResponseRetriedWithoutSecondEffect, true);
assert.equal(final.status, 'COMPLETED');
assert.equal(final.rows.length, 6);
assert.equal(first.rows.length, 5);
assert.deepEqual(final.rows.slice(0, 5), first.rows);
assert.equal(final.factSource.reportSha256, sha(bytes('http.json')));
assert.equal(final.resume.previousReportSha256, sha(bytes('latency-first.json')));
assert.deepEqual(first.config, final.config);
assert.deepEqual(first.assets, final.assets);
assert.equal(final.config.cachePrompt, false);
assert.equal(final.rows.filter((row) => final.rowProvenance[row.id] === 'current_run').length, 1);
for (const row of final.rows) {
  const profile = row.id === 'narration-focused' ? final.source : first.source;
  for (const [path, digest] of Object.entries(profile.sha256)) {
    assert.equal(manifest.sourceProfiles[row.id === 'narration-focused' ? 'latencyResumed' : 'latencyFirst'].files[path].recordedWorkingSha256, digest);
  }
  const reviewed = review.modelCandidateReviews.find((item) => item.id === row.id);
  assert.equal(reviewed.raw, row.completion.raw);
  if (row.completion.timings) assert.equal(row.completion.timings.cache_n, 0);
  else { assert.equal(row.completion.finishReason, 'timeout'); assert.equal(row.failure, 'engine'); }
}
for (const task of ['action', 'updates', 'narration']) {
  assert.deepEqual(final.rows.find((row) => row.id === `${task}-full`).input,
    final.rows.find((row) => row.id === `${task}-focused`).input);
}
assert.equal(review.modelCandidateReviews.find((row) => row.id === 'action-full').acceptedCandidate, false);
assert.equal(review.modelCandidateReviews.find((row) => row.id === 'narration-focused').acceptedCandidate, false);
assert.equal(selection.paidModelCalls, 0);
assert.equal(selection.selection.accepted, false);
assert.equal(selection.selection.text, http.rows.find((row) => row.id === 'move').narration.text);
assert.equal(selection.candidate, final.rows.find((row) => row.id === 'narration-focused').completion.raw);
assert.equal(final.cleanup.browserClosed, true); assert.equal(final.cleanup.serverClosed, true);
assert.equal(first.cleanup.browserClosed, true); assert.equal(first.cleanup.serverClosed, true);
console.log('PASS: artifact/source hashes, 10 single-commit rule worlds, saved templates, 5+1 preserved model calls, and explicit failures');
