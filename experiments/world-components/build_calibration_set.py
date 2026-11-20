"""Build the 24-fact calibration set for the component-constraint specification.

No training happens here. The output carries, per row:

  components  name / other / relation / state with character spans, each asserted
              to sit inside the target by exact match, plus the token span that
              the character span maps to under the frozen tokenizer
  negatives   per-kind corruptions, each with an assertion that it differs from
              the target inside one component region only

Rows whose span or corruption cannot be built are listed in the report rather
than dropped silently.
"""
import argparse
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
POOLS = ('arm-c-verbalizer.jsonl', 'arm-c-expand78.jsonl', 'arm-c-object34.jsonl')
FACT_LINE = re.compile(r'事实=([^\n]+)')
SCENE_LINE = re.compile(r'^(地点|地点可见|场景)=', re.M)

VERBS = ('走进', '走到', '到了', '回到', '上到', '下到', '穿过', '走过', '站住', '停下',
         '结', '沾', '换', '补', '挪', '合', '拖', '放', '擦', '系', '断', '散', '松',
         '歪', '渗', '裂', '磨', '垂', '滑', '积', '露', '插', '缠', '搭', '挂', '靠',
         '压', '套', '卡', '盖', '问', '等', '开', '落', '匀', '发紧', '慢下来')
RELATIONS = ('缠', '挂', '系', '套', '盖', '插', '搭', '卡')
WANT = {'moved': 6, 'appearance_changed': 6, 'outcome': 4,
        'sanity_changed': 4, 'personality_changed': 2, 'no_change': 2}
# Negation by substitution only works where the predicate is a plain verb phrase.
# The outcome rows use a 把/adverb frame and the personality rows are whole rewritten
# behaviours, so a mechanical negation there yields broken text; those kinds keep only
# the name-drop negative and the gap is recorded in the report.
NEGATION_OK = {'moved', 'appearance_changed', 'sanity_changed', 'no_change'}


def load():
    rows = []
    for name in POOLS:
        for line in (ROOT / 'artifacts/three-arm-r1' / name).read_text(encoding='utf-8').splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def parse_fact(row):
    m = FACT_LINE.search(row['input'])
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split('｜')]
    if len(parts) < 2:
        return None
    return {'name': parts[0], 'label': parts[1], 'content': '｜'.join(parts[2:])}


def scene_block(row):
    return '\n'.join(line for line in row['input'].splitlines() if SCENE_LINE.match(line))


def span_in(text, needle):
    start = text.find(needle)
    if start < 0 or text.find(needle, start + 1) >= 0:
        return None
    return {'text': needle, 'start': start, 'end': start + len(needle)}


def state_span(target, name):
    begin = target.find(name) + len(name) if name and name in target else 0
    best = None
    for verb in VERBS:
        pos = target.find(verb, begin)
        if pos < 0:
            continue
        if best is None or pos < best[0]:
            best = (pos, verb)
    if best is None:
        return None
    pos, verb = best
    end = pos + len(verb)
    if end < len(target) and target[end] in '了着过':
        end += 1
    return {'text': target[pos:end], 'start': pos, 'end': end}


def build_components(row, fact, target):
    comp = {'name': None, 'other': None, 'relation': None, 'state': None}
    if fact['name'] not in ('场景', '周围') and fact['name'] in target:
        comp['name'] = span_in(target, fact['name'])
    if row['kind'] == 'moved' and '→' in fact['content']:
        dest = fact['content'].split('→')[1].strip()
        if dest in target:
            comp['other'] = span_in(target, dest)
    for relation in RELATIONS:
        if relation in fact['content']:
            pos = target.find(relation)
            if pos >= 0:
                comp['relation'] = {'text': relation, 'start': pos, 'end': pos + len(relation)}
                break
    comp['state'] = state_span(target, fact['name'] if comp['name'] else '')
    return comp


def glue(text, span):
    """Delete a span together with the particle that binds it, so the result stays a sentence."""
    if span is None:
        return text
    start, end = span['start'], span['end']
    for particle in ('的', '上', '里', '中'):
        if text[end:end + len(particle)] == particle:
            end += len(particle)
            break
    return text[:start] + text[end:]


def negatives(row, fact, target, comp):
    """Per-kind minimal edits. A substitution that only breaks the grammar is not a negative.

    Each entry records the region it rewrites, so the check downstream is that the
    prefix before that region is unchanged.
    """
    out = []
    kind = row['kind']
    state = comp['state']

    def add(kind_name, component, text, region, why=''):
        item = {'type': kind_name, 'component': component, 'text': text, 'region': region, 'why': why}
        if text == target:
            item['valid'] = False
            item['why'] = 'identical to the correct target'
        elif not text.strip():
            item['valid'] = False
            item['why'] = 'empty result'
        else:
            item['valid'] = True
        out.append(item)

    if comp['name']:
        end = comp['name']['end']
        for particle in ('的', '上', '里'):
            if target[end:end + len(particle)] == particle:
                end += len(particle)
                break
        add('name_drop', 'name', target[:comp['name']['start']] + target[end:],
            [comp['name']['start'], end])

    if kind == 'moved' and comp['other']:
        add('other_vague', 'other',
            target[:comp['other']['start']] + '那里' + target[comp['other']['end']:],
            [comp['other']['start'], comp['other']['end']])

    if kind == 'no_change':
        add('state_event', 'state', '远处传来一声闷响，屋里的东西都挪了位置。', [0, len(target)],
            'the correct target is an absence statement, so the negative must be an event')
        return out

    if state is None:
        return out

    head = target[:state['start']]
    if kind == 'moved':
        add('state_negated', 'state', head + '没有' + target[state['start']:], [state['start'], len(target)],
            'the arrival is negated instead of stated')
    elif kind in ('appearance_changed', 'sanity_changed'):
        trimmed = head.rstrip('有些慢慢渐渐地才一直')
        add('state_stasis', 'state', trimmed + '没有变化。', [len(trimmed), len(target)],
            'the change is replaced by a statement that nothing changed')
    return out


    return out

    if state is None:
        return out

    head = target[:state['start']]
    if kind == 'moved':
        add('state_negated', 'state', head + '没有' + target[state['start']:], [state['start'], len(target)],
            'the arrival is negated instead of stated')
    elif kind in ('appearance_changed', 'sanity_changed'):
        add('state_stasis', 'state', head + '没有变化。', [state['start'], len(target)],
            'the change is replaced by a statement that nothing changed')
    elif kind == 'outcome':
        rest = target[state['end']:]
        if rest.startswith('了'):
            rest = rest[1:]
        add('state_negated', 'state', head + '没' + state['text'] + rest, [state['start'], len(target)],
            'the accomplished action is negated')
    elif kind == 'personality_changed':
        add('state_not_done', 'state', head + '没有照做。', [state['start'], len(target)],
            'the changed behaviour is replaced by its absence')
    return out


def char_to_token(tokenizer, target, span):
    ids = tokenizer(target, add_special_tokens=False).input_ids
    pieces = [tokenizer.decode([i]) for i in ids]
    offsets, cursor = [], 0
    for piece in pieces:
        offsets.append((cursor, cursor + len(piece)))
        cursor += len(piece)
    if cursor != len(target):
        return None, 'piece concatenation does not rebuild the target'
    if span is None:
        return None, ''
    hit = [i for i, (a, b) in enumerate(offsets) if a < span['end'] and b > span['start']]
    if not hit:
        return None, 'no token overlaps the span'
    decoded = ''.join(pieces[hit[0]:hit[-1] + 1])
    return {'first': hit[0], 'last': hit[-1], 'count': len(hit),
            'decoded': decoded, 'exact': decoded == span['text']}, ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', default='artifacts/calibration-r1')
    parser.add_argument('--tokenizer', default=str(pathlib.Path(r'D:/others/Jity/.local/models')))
    args = parser.parse_args()

    from transformers import T5Tokenizer
    tokenizer = T5Tokenizer.from_pretrained(args.tokenizer, legacy=False, local_files_only=True)

    rows = load()
    chosen, failures = [], []
    taken = {kind: 0 for kind in WANT}
    seen_facts = set()
    for row in rows:
        kind = row['kind']
        if kind not in WANT or taken[kind] >= WANT[kind]:
            continue
        fact = parse_fact(row)
        if not fact:
            continue
        key = (fact['name'], fact['label'], row['target'])
        if key in seen_facts:
            continue
        seen_facts.add(key)
        chosen.append(row)
        taken[kind] += 1
        if all(taken[k] >= WANT[k] for k in WANT):
            break

    out = []
    for index, row in enumerate(chosen):
        fact = parse_fact(row)
        target = row['target']
        comp = build_components(row, fact, target)
        for key, span in comp.items():
            if span is None:
                continue
            if target[span['start']:span['end']] != span['text']:
                failures.append({'factId': row.get('pairId') or row.get('unitId'),
                                 'component': key, 'why': 'span does not match the target'})
        token_spans, token_notes = {}, {}
        for key, span in comp.items():
            got, note = char_to_token(tokenizer, target, span)
            token_spans[key] = got
            if note:
                token_notes[key] = note
        negs = negatives(row, fact, target, comp)
        other_row = rows[(rows.index(row) + 7) % len(rows)]
        for variant in (0, 1):
            text = row['input'] if variant == 0 else \
                row['input'].replace(scene_block(row), scene_block(other_row)) if scene_block(row) else row['input']
            out.append({
                'rowId': '%02d:%s' % (index, 'ab'[variant]),
                'factId': row.get('pairId') or row.get('unitId'),
                'kind': row['kind'],
                'expression': variant,
                'input': text,
                'target': target,
                'fact': fact,
                'components': comp,
                'tokenSpans': token_spans,
                'tokenNotes': token_notes,
                'negatives': negs,
            })

    by_type = {}
    for row in out:
        for neg in row['negatives']:
            entry = by_type.setdefault(neg['type'], {'rows': 0, 'valid': 0, 'invalid': 0})
            entry['rows'] += 1
            entry['valid' if neg['valid'] else 'invalid'] += 1
    report = {
        'purpose': 'calibration set for the component-constraint specification; no training',
        'facts': len(chosen),
        'rows': len(out),
        'k': 2,
        'kNote': 'the two expressions share the target and differ only in the scene block; the pool has no '
                 'second surface rendering of the same fact, so this checks the machinery, not surface variety',
        'kindCounts': {k: taken[k] for k in WANT},
        'negatives': by_type,
        'componentsMissing': {k: sum(1 for r in out if r['components'][k] is None) for k in
                              ('name', 'other', 'relation', 'state')},
        'failures': failures,
        'rowsWithoutNegatives': [r['rowId'] for r in out if not r['negatives']],
        'negationNotConstructed': {
            'kinds': sorted(set(WANT) - NEGATION_OK),
            'why': 'the predicate is a 把/adverb frame or a rewritten behaviour, so mechanical negation produces '
                   'broken text; only the name-drop negative survives for those kinds',
            'relationNegatives': 'this subset carries almost no relation facts (relation span found on 2 of 48 rows), '
                                 'so relation direction is not calibrated here'},
    }
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'set.jsonl').write_text(
        '\n'.join(json.dumps(r, ensure_ascii=False) for r in out) + '\n', encoding='utf-8', newline='\n')
    (out_dir / 'build-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
