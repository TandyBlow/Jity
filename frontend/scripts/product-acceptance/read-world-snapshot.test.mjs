import test from 'node:test';
import assert from 'node:assert/strict';
import { readWorldSnapshot } from './read-world-snapshot.mjs';

test('returns null when snapshot is unavailable', () => {
  const old = globalThis.__worldSnapshot;
  try {
    delete globalThis.__worldSnapshot;
    assert.equal(readWorldSnapshot(), null);
  } finally {
    if (old !== undefined) globalThis.__worldSnapshot = old;
  }
});

test('reads both historical objects and the current live getter', () => {
  const old = globalThis.__worldSnapshot;
  try {
    const first = { transport: { version: 1 } };
    globalThis.__worldSnapshot = first;
    assert.equal(readWorldSnapshot(), first);
    let current = first;
    globalThis.__worldSnapshot = () => structuredClone(current);
    assert.deepEqual(readWorldSnapshot(), first);
    current = { transport: { version: 2 } };
    const saved = readWorldSnapshot();
    assert.deepEqual(saved, current);
    assert.equal(typeof saved, 'object');
    assert.equal(JSON.parse(JSON.stringify(saved)).transport.version, 2);
  } finally {
    if (old === undefined) delete globalThis.__worldSnapshot;
    else globalThis.__worldSnapshot = old;
  }
});
