import assert from 'node:assert/strict';
import { combinations } from './arms';

const items = [17, 29, 43, 61, 79, 97];

assert.equal(combinations(items, 0).length, 0);
assert.equal(combinations(items, 7).length, 0);
assert.equal(combinations(items, 1).length, 6);
assert.equal(combinations(items, 2).length, 15);
assert.equal(combinations(items, 4).length, 15);
assert.equal(combinations(items, 6).length, 1);

const singles = combinations(items, 1).map((subset) => subset[0]).sort((a, b) => a - b);
assert.deepEqual(singles, items, 'N=1 must cover every seed, not only the first one');

const pairs = combinations(items, 2);
assert.deepEqual(pairs[0], [17, 29]);
assert.deepEqual(pairs[pairs.length - 1], [79, 97]);
for (const pair of pairs) assert.equal(new Set(pair).size, 2);

const quadruples = combinations(items, 4);
assert.equal(new Set(quadruples.map((subset) => subset.join(','))).size, 15);
assert.ok(quadruples.every((subset) => subset.length === 4));

console.log('arms.test: ok (C(6,1)=6, C(6,2)=15, C(6,4)=15; every seed in N=1)');
