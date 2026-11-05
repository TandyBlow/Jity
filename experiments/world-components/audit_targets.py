"""Audit every training pair against its own fact statement.

This does not change any pool file. It reads the three pools that feed the
two-arm continuation (229 + 78 + 34 = 341 pairs), runs fixed mechanical checks,
and writes one record per pair so a human can adjudicate the flagged ones.

Checks (each becomes a flag; a pair with any flag needs manual review):

  subject        the fact's subject name (or an alias) must appear in the target
  value-cover    bigram coverage of the fact value below 0.5
  quantity       a measure word in the fact value (一叠, 一筐, 一小摞) is missing
                 from the target
  qualifier      a two-character-or-longer noun of the fact value that names a
                 place or prop is missing from the target
  endpoint       moved facts need both the start and the destination, by name or
                 alias
  extra-clause   a second clause whose own coverage of the fact value is below
                 0.34, i.e. it looks like an added event
  place          a world place appears that is neither the current location, a
                 sublocation of it, nor a movement endpoint
  cue            a state change has no perceptible cue (body, breath, pace,
                 voice)
  nochange       a no-change fact lacks a no-change expression
  banned         digits, durations or a task title leaked into the target

Output: artifacts/target-audit-r1/audit-r1.json plus a printable list of flagged
pairs. Manual verdicts live in audit_decisions.py, not here.
"""
import collections
import hashlib
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]
OUT = WORKTREE / 'artifacts/target-audit-r1'
POOLS = (('verbalizer', WORKTREE / 'experiments/world-components/n4_narrative_dev/verbalizer_pairs.jsonl'),
         ('expand78', WORKTREE / 'artifacts/next-inputs/world-components/n4-expand78-unified.jsonl'),
         ('object34', WORKTREE / 'artifacts/next-inputs/world-components/n4-object34-unified.jsonl'))

ALIASES = {'潮汐档案馆': ['档案馆'], '潮渡': ['渡口'], '旧灯塔': ['灯塔'], '雾堤': ['堤面', '堤上'],
           '潮生巷': ['巷子'], '早市': ['集市'], '帆布棚': ['摊棚'], '银鳞鱼': ['鱼']}
PEOPLE = {'沈砚', '叶知微', '阿棠', '韩渡'}
PUNCT = re.compile(r'[\s，,。．.；;：:！!？?、…—－\-\'"“”‘’（）()《》「」]')
MEASURE = re.compile(r'一小摞|一叠|一筐|一摞|一层|一圈|一片|一道|一股|一把|一截|半点')
CUE = re.compile(r'手|肩|呼吸|背|拳|步子|脚步|眼神|胸口|腰|声音|语速|下颌|喉咙|眉|指尖|掌心|袖口|衣摆|鞋底|辫梢')
NO_CHANGE = re.compile(r'原处|没有新的变化|没有别的动静|什么也没有再发生|没有新的事情|没变|照旧|还是|没动|纹丝不动|一如往常|安静')
BANNED = re.compile(r'\d|[一二三四五六七八九十]+\s*(?:秒|分钟|小时|刻|步|次|下)\s*[，,。]|任务')
CLAUSE = re.compile(r'[，,]')


def load(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def normalize(text):
    return PUNCT.sub('', text or '')


def bigrams(text):
    flat = normalize(text)
    return {flat[i:i + 2] for i in range(len(flat) - 1)}


def coverage(value, target):
    wanted = bigrams(value)
    if not wanted:
        return 1.0
    return len(wanted & bigrams(target)) / len(wanted)


def field(lines, prefix):
    for line in lines:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ''


def parse(pair):
    lines = pair['input'].splitlines()
    fact = field(lines, '事实=')
    parts = [p.strip() for p in fact.split('｜')]
    record = {'location': field(lines, '地点='), 'visible': field(lines, '地点可见='),
              'scene': field(lines, '场景='), 'direction': field(lines, '方向='),
              'fact_text': fact, 'subject': parts[0] if parts else '',
              'fact_kind': parts[1] if len(parts) > 1 else '', 'value': parts[2] if len(parts) > 2 else ''}
    record['from'], record['to'] = '', ''
    if '→' in record['value']:
        record['from'], record['to'] = (s.strip() for s in record['value'].split('→', 1))
    return record


def world():
    data = json.loads((HERE / 'n4_narrative_dev' / 'world.json').read_text(encoding='utf-8'))
    places, children = set(), {}
    for location in data['locations'].values():
        name = location['name']
        places.add(name)
        kids = [sub['name'] for sub in location.get('sublocations', [])]
        children[name] = set(kids)
        places.update(kids)
    return places, children


def spoken(name):
    return [name] + ALIASES.get(name, [])


def says(text, name):
    return any(word in text for word in spoken(name))


def authorised(place, allowed, children):
    if place in allowed:
        return True
    for name in allowed:
        if place in children.get(name, set()) or place in ALIASES.get(name, []):
            return True
        if name in children.get(place, set()) or name in ALIASES.get(place, []):
            return True
    return False


def audit(pair, places, children):
    meta = parse(pair)
    target = pair['target']
    kind = pair['kind']
    flags = []
    if meta['subject'] in PEOPLE or meta['subject'] in places:
        if not says(target, meta['subject']):
            flags.append('subject')
    if kind == 'moved':
        for endpoint in (meta['from'], meta['to']):
            if endpoint and not says(target, endpoint):
                flags.append('endpoint:' + endpoint)
    elif kind in ('outcome', 'appearance_changed', 'personality_changed'):
        if coverage(meta['value'], target) < 0.5:
            flags.append('value-cover:%.2f' % coverage(meta['value'], target))
        for measure in MEASURE.findall(meta['value']):
            if measure not in target:
                flags.append('quantity:' + measure)
        for token in re.findall(r'[\u4e00-\u9fa5]{2,}', normalize(meta['value'])):
            if token in ('移动', '结果', '外貌变化', '性格变化'):
                continue
            if any(token in item for item in re.split(r'[、,，；;]', meta['visible'])):
                if token not in normalize(target):
                    flags.append('qualifier:' + token)
    elif kind == 'sanity_changed':
        if not CUE.search(target):
            flags.append('cue')
    elif kind == 'no_change':
        if not NO_CHANGE.search(target):
            flags.append('nochange')
    clauses = [c for c in CLAUSE.split(target) if len(normalize(c)) >= 3]
    if len(clauses) > 1:
        worst = min(coverage(meta['value'], c) for c in clauses[1:])
        if kind != 'moved' and worst < 0.34:
            flags.append('extra-clause:%.2f' % worst)
        if kind == 'moved' and not any(says(c, meta['to']) for c in clauses[1:]):
            flags.append('extra-clause:tail')
    allowed = set(re.split(r'[>＞]', meta['location'])) | {meta['from'], meta['to']} - {''}
    for prop in re.split(r'[、,，；;]', meta['visible']):
        if prop.strip():
            allowed.add(prop.strip())
    for place in sorted(places):
        if place in target and not authorised(place, allowed, children) and place not in meta['fact_text']:
            flags.append('place:' + place)
    if BANNED.search(target):
        flags.append('banned')
    return {'pool_source': pair.get('pairId') or pair.get('unitId'), 'kind': kind, 'target': target,
            'fact': meta['fact_text'], 'location': meta['location'], 'value': meta['value'],
            'subject': meta['subject'], 'from': meta['from'], 'to': meta['to'],
            'coverage': round(coverage(meta['value'], target), 3),
            'flags': flags, 'status': 'review' if flags else 'machine-clean'}


def main():
    places, children = world()
    rows, per_pool = [], collections.Counter()
    digests = {}
    for pool, path in POOLS:
        pairs = load(path)
        digests[pool] = hashlib.sha256(path.read_bytes()).hexdigest()
        for pair in pairs:
            record = audit(pair, places, children)
            record['pool'] = pool
            rows.append(record)
            per_pool[pool] += 1
    flagged = [r for r in rows if r['flags']]
    reasons = collections.Counter(f.split(':')[0] for r in flagged for f in r['flags'])
    report = {'pools': {pool: {'rows': n, 'sha256': digests[pool]} for pool, n in per_pool.items()},
              'rows': len(rows), 'flagged': len(flagged),
              'flagCounts': dict(sorted(reasons.items())),
              'records': rows}
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'audit-r1.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    for record in flagged:
        print('%-12s %-18s cov %.2f %-28s | %s' % (record['pool'], record['pool_source'],
                                                   record['coverage'], ','.join(record['flags']),
                                                   record['target']))
    print('rows %d flagged %d -> %s' % (len(rows), len(flagged), target.relative_to(WORKTREE)))


if __name__ == '__main__':
    main()
