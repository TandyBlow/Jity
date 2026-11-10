import assert from 'node:assert/strict';
import { firstPersonNarration } from './viewpoint';

const third = { 视角: '主角视角（温执）；只表达已结算的世界事实' };

assert.equal(firstPersonNarration(third, '我站在还书处，箱底垫着一块木板。').flagged, true);
assert.deepEqual(
  firstPersonNarration(third, '我站在还书处，箱底垫着一块木板。').sentences,
  ['我站在还书处，箱底垫着一块木板。'],
);
assert.equal(firstPersonNarration(third, '温执站在还书处，箱底垫着一块木板。').flagged, false);
assert.equal(firstPersonNarration(third, '温执说：“我走了。”').flagged, false);
assert.equal(firstPersonNarration(third, '温执说：“我走了。”我跟着走了。').flagged, true);
assert.equal(firstPersonNarration({ 视角: '第一人称视角（温执）' }, '我站在还书处。').flagged, false);
assert.equal(firstPersonNarration({}, '我站在还书处。').flagged, false);
assert.equal(firstPersonNarration(third, '他把我留在还书处。').flagged, false);

console.log('viewpoint.test: ok (first-person narration guarded; quoted dialogue and explicit first person allowed)');
