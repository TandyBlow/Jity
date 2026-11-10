/** Text-level checks shared by the three handlers.
 *
 * These are guards, not language understanding: they only reject output that
 * cannot be an action of the declared actor (verbatim echo of the player's
 * words, first person, dialogue attributed to the wrong character). They
 * never decide *who* acts, *whom* the action touches or *what* the reaction
 * says — those stay with the model.
 */

const QUOTE_PAIRS: [string, string][] = [['“', '”'], ['"', '"'], ['「', '」'], ['‘', '’'], ['『', '』']];

/** NFC, whitespace collapsed, trimmed. Comparison form for every guard. */
export function normalize(text: string): string {
  return text.normalize('NFC').replace(/[\s\u3000]+/gu, ' ').trim();
}

/** Characters that never distinguish copying from paraphrase. They are
 * stripped from the span comparison so punctuation edits cannot launder a
 * verbatim repeat. */
const SKELETON_STRIP = /[\s\u3000，。；：、！？…—–\-·,.;:!?()（）【】\[\]《》<>"'“”‘’「」『』]/gu;

export function skeleton(text: string): string {
  return normalize(text).replace(SKELETON_STRIP, '');
}

/** Splits quoted speech out of a line. `plain` is the narration with the
 * quoted spans removed (so attribution checks never fire on dialogue). */
export function splitQuotes(text: string): { plain: string; quotes: string[] } {
  let plain = normalize(text);
  const quotes: string[] = [];
  for (const [open, close] of QUOTE_PAIRS) {
    let index = plain.indexOf(open);
    while (index >= 0) {
      const end = plain.indexOf(close, index + open.length);
      if (end < 0) break;
      const inner = plain.slice(index + open.length, end).trim();
      if (inner) quotes.push(inner);
      plain = `${plain.slice(0, index)} ${plain.slice(end + close.length)}`;
      index = plain.indexOf(open);
    }
  }
  return { plain: normalize(plain), quotes };
}

export interface SharedSpan {
  length: number;
  text: string;
}

/** Longest common contiguous span on skeletons (O(n·m), capped small enough
 * for the 500-char inputs this module accepts). */
export function longestSharedSpan(a: string, b: string): SharedSpan {
  const left = [...skeleton(a)];
  const right = [...skeleton(b)];
  if (!left.length || !right.length) return { length: 0, text: '' };
  let best = 0;
  let bestEnd = 0;
  let previous = new Uint16Array(right.length + 1);
  let current = new Uint16Array(right.length + 1);
  for (let i = 1; i <= left.length; i += 1) {
    for (let j = 1; j <= right.length; j += 1) {
      if (left[i - 1] === right[j - 1]) {
        const value = previous[j - 1] + 1;
        current[j] = value;
        if (value > best) {
          best = value;
          bestEnd = i;
        }
      } else {
        current[j] = 0;
      }
    }
    const swap = previous;
    previous = current;
    current = swap;
    current.fill(0);
  }
  return { length: best, text: left.slice(bestEnd - best, bestEnd).join('') };
}

const PRONOUN = /他们|她们|它们|他|她|它|对方|那人|这人|这个人|那个人|这位|那位|两人|二人|众人|来人|别人/u;
const DEICTIC = /面前|身边|对面|旁边|眼前|门口|身后|手里|身上|这里|那里/u;

/** True when the action text has an anaphor/deictic instead of a name — the
 * case where a program name-match would be blind but a model reading the
 * scene is not. Used only for evidence and one soft warning. */
export function hasAnaphora(text: string): boolean {
  const { plain } = splitQuotes(text);
  return PRONOUN.test(plain) || DEICTIC.test(plain);
}

export function hasPronounOnly(text: string): boolean {
  const { plain } = splitQuotes(text);
  return PRONOUN.test(plain);
}

const SPEECH_VERB = /(说|问|答|喊|叫|道|嘟囔|低声|大声|开口|回答|解释|提醒|告诉|表示|承认|否认)/u;

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** First unquoted occurrence of 我. Dialogue may say 我; narration may not
 * (the action text is third-person about the actor). */
export function firstPersonOutsideQuotes(text: string): boolean {
  return splitQuotes(text).plain.includes('我');
}

/** Actor attribution: the text opens with `name` and attributes speech to it.
 * Catches "路明非说：……" handed in for another character. */
export function speaksAs(text: string, name: string): boolean {
  const { plain } = splitQuotes(text);
  if (!name) return false;
  const pattern = new RegExp(`^${escapeRegExp(name)}[^，。；！？]{0,4}?${SPEECH_VERB.source}`, 'u');
  return pattern.test(plain);
}

/** Text opens with a name (subject position), regardless of the verb. */
export function startsWithName(text: string, name: string): boolean {
  if (!name) return false;
  return splitQuotes(text).plain.trimStart().startsWith(name);
}

/** Quoted spans long enough to be a copied sentence rather than a shared
 * 2-character exclamation. */
export function longQuotes(text: string, minLength = 4): string[] {
  return splitQuotes(text).quotes.filter((quote) => [...quote].length >= minLength);
}
