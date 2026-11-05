"""Mechanical first pass over a cf24 baseline run.

The rules are the frozen ones, restated here so a run can be re-judged later:

  * moved counts as supported only when BOTH the start and the destination are
    written (v2-strict-moved);
  * sanity counts only with a perceptible direction; writing "上升/下降" or the
    bare value is a miss;
  * no_change needs one of the fixed "nothing new happened" phrasings;
  * every other fact needs the subject's name plus >= 0.5 character-bigram
    coverage of its value text.

On top of the verdicts it flags what the verdict rule does not measure: a
second clause that repeats the first, a doubled "的", an extra clause after the
fact, a character or place that the unit never mentions. Those flags are
prompts for review, not verdicts.
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from component_paths import ComponentPaths  # noqa: E402

PUNCT = re.compile(r'[\s，,。．.；;：:！!？?、…—－\-\'"“”‘’（）()《》「」]')
ALIASES = {'潮汐档案馆': ['档案馆'], '潮渡': ['渡口', '栈桥'], '旧灯塔': ['灯塔'], '雾堤': ['堤面', '堤上'],
           '潮生巷': ['巷子'], '早市': ['集市']}
SANITY_UP = ['匀', '松', '散', '落回', '慢下来', '稳', '缓']
SANITY_DOWN = ['发紧', '发闷', '重', '不听使唤', '冷汗', '屏', '抖']
NO_CHANGE = re.compile(r'(没有新的变化|没有新的事情|什么也没有再发生|没有别的动静|没有动静|没有动)')


def normalize(text):
    return PUNCT.sub('', text or '')


def bigrams(text):
    flat = normalize(text)
    return {flat[i:i + 2] for i in range(len(flat) - 1)}


def coverage(key, text):
    key_grams = bigrams(key)
    return len(key_grams & bigrams(text)) / len(key_grams) if key_grams else 1.0


def world_names():
    world = json.loads((HERE / 'n4_narrative_dev' / 'world.json').read_text(encoding='utf-8'))
    people = {c['name'] for c in world['characters'].values()}
    places = {p['name'] for p in world['locations'].values()}
    for place in world['locations'].values():
        places.update(sub['name'] for sub in place.get('sublocations', []))
    return people, places


def clause_split(text):
    return [part for part in re.split(r'[，,。；;]', text or '') if part.strip()]


def judge(unit, text):
    fact = unit['fact']
    kind = unit['kind']
    name = fact.get('name') or ''
    flags = []
    if kind == 'no_change':
        ok = bool(NO_CHANGE.search(text))
        return ('S' if ok else 'O'), ('无变化表述缺失' if not ok else ''), flags
    seen_place = lambda place: bool(place) and (place in text or any(a in text for a in ALIASES.get(place, [])))
    if kind == 'moved':
        start, end = fact.get('from'), fact.get('to')
        if seen_place(start) and seen_place(end):
            verdict, note = 'S', ''
        else:
            verdict = 'O'
            note = '起点%s 终点%s' % ('有' if seen_place(start) else '缺', '有' if seen_place(end) else '缺')
        return verdict, note, flags
    if kind == 'sanity_changed':
        rising = fact['to'] > fact['from']
        cue = any(word in text for word in (SANITY_UP if rising else SANITY_DOWN))
        if re.search(r'(%s)(放松|发紧|上升|下降)' % re.escape(name), text):
            return 'O', '值词直写', flags
        return ('S' if cue else 'O'), ('' if cue else '无方向'), flags
    key = fact.get('resultText') or fact.get('text') or ''
    if name and name not in text:
        return 'A', '主体缺失(%s)' % name, flags
    covered = coverage(key, text)
    if covered >= 0.5:
        return 'S', '覆盖%.2f' % covered, flags
    if covered >= 0.25:
        return 'REVIEW', '覆盖%.2f' % covered, flags
    return 'O', '覆盖%.2f' % covered, flags


def parse_context(unit):
    """Places and visible props the unit input itself authorises."""
    place_line = re.search(r'地点=([^\n]*)', unit['input'])
    visible_line = re.search(r'地点可见=([^\n]*)', unit['input'])
    places = set()
    if place_line:
        for part in re.split(r'[>、,，]', place_line.group(1)):
            part = part.strip()
            if part:
                places.add(part)
    visible = set()
    if visible_line:
        for part in re.split(r'[、,，]', visible_line.group(1)):
            part = part.strip()
            if part:
                visible.add(part)
    return places, visible


def moved_tail(text, fact):
    """Clauses after the first that carry neither the start nor the destination."""
    start, destination = fact.get('from'), fact.get('to')
    body = text.rstrip('。')
    parts = [part for part in re.split(r'(?<=[，,])', body)]
    extra = []
    for clause in parts[1:]:
        if not (carries(clause, start) or carries(clause, destination)):
            extra.append(clause.rstrip('，,、 '))
    return extra


def carries(text, place):
    if not place:
        return False
    return place in text or any(alias in text for alias in ALIASES.get(place, []))


def extra_flags(unit, text):
    flags = []
    clauses = clause_split(text)
    if len(clauses) > 1:
        first = clauses[0]
        for later in clauses[1:]:
            if bigrams(later) and len(bigrams(later) & bigrams(first)) >= 3:
                flags.append('repeat:' + later)
                break
    if re.search(r'的[^的，。]{1,3}的', text):
        flags.append('double-de')
    if unit['kind'] == 'moved':
        for clause in moved_tail(text, unit['fact']):
            flags.append('extra-tail:' + clause)
    people, places = world_names()
    subject = unit['fact'].get('name') or ''
    fact = unit['fact']
    allowed_places, visible = parse_context(unit)
    allowed_places |= {fact.get('from'), fact.get('to')} - {None}
    fact_text = json.dumps(fact, ensure_ascii=False)
    for person in sorted(people):
        if person in text and person != subject and person not in fact_text:
            flags.append('other-actor:' + person)
    for place in sorted(places):
        if place in text and place not in allowed_places and place not in fact_text:
            flags.append('other-place:' + place)
    return flags


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--file', default='cf24-baseline.json',
                        help='Run output to score; edited runs use cf24-edited.json')
    args = parser.parse_args()
    paths = ComponentPaths()
    run_dir = paths.output(args.run_dir)
    source = run_dir / args.file
    if not source.is_file():
        raise SystemExit(f'Missing baseline output: {source}')
    report = json.loads(source.read_text(encoding='utf-8'))

    rows, per_source = [], {}
    counts = {'S': 0, 'O': 0, 'A': 0, 'REVIEW': 0}
    for row in report['rows']:
        verdict, note, _ = judge(row, row['text'])
        flags = extra_flags(row, row['text'])
        counts[verdict] += 1
        rows.append({'unitId': row['unitId'], 'sourceId': row['sourceId'], 'kind': row['kind'],
                     'text': row['text'], 'verdict': verdict, 'note': note, 'flags': flags})
        entry = per_source.setdefault(row['sourceId'], {'verdicts': {}, 'flags': []})
        entry['verdicts'].setdefault(row['unitId'].split(':')[1], verdict)
        entry['flags'].extend(flags)

    clean = sum(1 for s in per_source.values()
                if all(v == 'S' for v in s['verdicts'].values()) and not s['flags'])
    summary = {'scoringVersion': 'cf24-mechanical-v2-strict-moved',
               'note': 'mechanical first pass; flags need review',
               'facts': counts,
               'sources': len(per_source),
               'cleanSources': clean,
               'sourcesWithFlags': sum(1 for s in per_source.values() if s['flags'])}
    out = {'summary': summary, 'rows': rows, 'perSource': per_source,
           'scoredFile': args.file}
    target = run_dir / ('cf24-mechanical.json' if args.file == 'cf24-baseline.json'
                        else 'cf24-mechanical-' + pathlib.Path(args.file).stem + '.json')
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print('->', target)


if __name__ == '__main__':
    main()
