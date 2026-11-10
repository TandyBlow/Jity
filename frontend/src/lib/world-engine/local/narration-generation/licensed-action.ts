/** Unlicensed actions: a posture or a hand on a thing the input did not move.
 *
 * The accepted 1.7B draft still said the viewpoint leant on a wall, "held" the
 * exercise vest, felt the route map "hot in his palm" and had hair brush his
 * goggles, while the serialized input says the goggles hang on his chest and
 * the map is posted on the wall. Those are new physical events, not style.
 *
 * Narrow by design:
 * - a fixed list of posture verbs and a fixed list of hand verbs;
 * - a posture verb is licensed when the same verb appears in the input;
 * - a hand verb is licensed when the object has no stated position in the
 *   input, or when the verb appears in the input next to that object.
 */
// Posture ("crouching", "leaning", "sitting") is a micro-action and is NOT a
// violation; only what changes a world fact is checked here.
export const OBJECT_MOVE_PHRASES = ['躺在地上', '倒在地上', '放在地上', '塞进兜里', '揣进兜里'] as const;
export const HAND_VERBS = ['握着', '握住', '拿着', '捏着', '攥着', '收起', '揣进', '摸向', '摸了摸', '摸着', '摘下', '戴上', '摘掉'] as const;

export interface ActionViolation {
  sentence: string;
  kind: 'hand' | 'position' | 'state';
  word: string;
  object?: string;
}

const SENTENCES = /[。！？\n]+/u;

const sentencesOf = (text: string): string[] =>
  text.split(SENTENCES).map((part) => part.trim()).filter(Boolean);

/** Objects whose position the input states, with the stated position phrase. */
function statedPositions(inputText: string): { name: string; position: string }[] {
  const found: { name: string; position: string }[] = [];
  // The position may sit in the parenthetical, after the colon, or both:
  // «路明非的护目镜（挂在胸前）：镜片无裂纹» states it in the brackets only,
  // so reading just the part after the colon missed it and a draft could put
  // the goggles in his hand without a violation.
  const reParen = new RegExp('([\u4e00-\u9fff]{2,10})\uff08([^\uff09]{1,30})\uff09(?:\uff1a([^\u3002\n]{0,60}))?', 'gu');
  for (const match of inputText.matchAll(reParen)) {
    found.push({ name: match[1], position: `${match[2]} ${match[3] ?? ''}` });
  }
  const reColon = new RegExp('([\u4e00-\u9fff]{2,10})(?:\uff08[^\uff09]{1,30}\uff09)?\uff1a([^\u3002\u3011]{0,80})', 'gu');
  for (const match of inputText.matchAll(reColon)) {
    const name = match[1];
    if (found.some((item) => item.name === name)) continue;
    found.push({ name, position: match[2] });
  }
  return found.filter((item) => /挂在|戴在|放在|压在|插在|装着|系在|收在|穿在|胸前|肩上|腰间|手里|袋里|兜里/u.test(item.position));
}

/** A scene state the input gives as already true («黄黑绳已放下»), with the
 * verb that produced it. Writing the change again («看着黄黑绳缓缓放下») is an
 * event the settlement never produced; the page showed exactly that. */
function completedStates(inputText: string): { name: string; verb: string }[] {
  const found: { name: string; verb: string }[] = [];
  const re = new RegExp('([一-鿿]{2,10}?)(?:已经|已)(放下|垂下|落下|打开|关上|关闭|收起|系好|熄灭|升起)', 'gu');
  for (const match of inputText.matchAll(re)) {
    const name = match[1].includes('的') ? match[1].slice(match[1].lastIndexOf('的') + 1) : match[1];
    if (name.length >= 2) found.push({ name, verb: match[2] });
  }
  return found;
}

export function actionViolations(text: string, inputText: string): ActionViolation[] {
  // Posture is deliberately NOT a violation: crouching, leaning or sitting are
  // micro-actions that change no world fact, and the product now keeps them.
  // A hand on someone else's property and an object that moves are the classes
  // that change what is true, so only those are returned as violations.
  const found: ActionViolation[] = [];
  const positions = statedPositions(inputText);
  const states = completedStates(inputText);
  const already = new RegExp('(?:已经|已)' + '', 'u');
  for (const sentence of sentencesOf(text)) {
    for (const state of states) {
      if (!sentence.includes(state.name) || !sentence.includes(state.verb)) continue;
      // «已经放下» restates the state; «缓缓放下» re-enacts it.
      if (sentence.includes('已经' + state.verb) || sentence.includes('已' + state.verb)) continue;
      found.push({ sentence, kind: 'state', word: state.verb, object: state.name });
    }
    for (const phrase of OBJECT_MOVE_PHRASES) {
      if (!sentence.includes(phrase) || inputText.includes(phrase)) continue;
      found.push({ sentence, kind: 'position', word: phrase });
    }
    // «把护目镜拿在手里»: the hand phrase follows the object, so a fixed verb
    // list misses it. A stated-position object in a sentence about the hand is
    // the same event as a hand verb.
    if (/(手中|手里|手上)/u.test(sentence)) {
      for (const object of positions) {
        const base = object.name.includes('的') ? object.name.slice(object.name.lastIndexOf('的') + 1) : object.name;
        if (base.length < 2 || !sentence.includes(base)) continue;
        if (/手里|手中|手上/u.test(object.position)) continue;
        found.push({ sentence, kind: 'hand', word: '手中', object: object.name });
        break;
      }
    }
    for (const verb of HAND_VERBS) {
      if (!sentence.includes(verb)) continue;
      for (const object of positions) {
        const base = object.name.includes('的') ? object.name.slice(object.name.lastIndexOf('的') + 1) : object.name;
        if (!sentence.includes(object.name) && !(base.length >= 2 && sentence.includes(base))) continue;
        // The input already has this hand on this thing: licensed.
        const near = inputText.indexOf(object.name);
        const window = inputText.slice(Math.max(0, near - 30), near + object.name.length + 30);
        if (window.includes(verb)) continue;
        found.push({ sentence, kind: 'hand', word: verb, object: object.name });
      }
    }
  }
  return found;
}
