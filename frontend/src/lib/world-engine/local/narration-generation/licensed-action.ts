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
// Sitting is left out on purpose: two of the 71 reference scenes sit down
  // without stating it, and a seat in the input is enough to make it true.
export const POSTURE_VERBS = ['蹲下', '蹲在', '靠在', '靠墙', '站起', '躺下'] as const;
export const HAND_VERBS = ['握着', '握住', '拿着', '捏着', '攥着', '收起', '揣进', '摸向', '摸了摸', '摸着'] as const;

export interface ActionViolation {
  sentence: string;
  kind: 'posture' | 'hand';
  word: string;
  object?: string;
}

const SENTENCES = /[。！？\n]+/u;

const sentencesOf = (text: string): string[] =>
  text.split(SENTENCES).map((part) => part.trim()).filter(Boolean);

/** Objects whose position the input states, with the stated position phrase. */
function statedPositions(inputText: string): { name: string; position: string }[] {
  const found: { name: string; position: string }[] = [];
  for (const match of inputText.matchAll(/([\u4e00-\u9fff]{2,10})（属于[^）]{1,10}）：([^。\n]{0,60})/gu)) {
    found.push({ name: match[1], position: match[2] });
  }
  for (const match of inputText.matchAll(/([\u4e00-\u9fff]{2,10})(?:（[^）]{1,20}）)?：([^。】]{0,80})/gu)) {
    const name = match[1];
    if (found.some((item) => item.name === name)) continue;
    found.push({ name, position: match[2] });
  }
  // Only things the input says are on/in/at a place: those are the ones a
  // sentence can put into a hand by mistake.
  return found.filter((item) => /挂在|戴在|放在|压在|插在|装着|系在|收在|穿在|胸前|肩上|腰间|手里|袋里|兜里/u.test(item.position));
}

export function actionViolations(text: string, inputText: string): ActionViolation[] {
  const found: ActionViolation[] = [];
  const positions = statedPositions(inputText);
  for (const sentence of sentencesOf(text)) {
    for (const verb of POSTURE_VERBS) {
      if (!sentence.includes(verb)) continue;
      if (inputText.includes(verb)) continue;
      found.push({ sentence, kind: 'posture', word: verb });
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
