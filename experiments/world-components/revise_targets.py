"""Build the revised training targets (r1) without touching the originals.

Only two defects are addressed, and only by deleting text:

  T1 moved tail   a clause after the movement that carries neither the start nor
                  the destination, so it adds an action or state the fact does
                  not contain;
  T2 extra fact   a trailing clause stating another fact (salt on a hand, ink on
                  a fingertip, a lantern corner lifting);
  T3 restatement  a trailing clause that says the result again (the rope going
                  taut after it was tied, the glass turning bright after it was
                  wiped).

Deletions are refused when they would remove the subject or a movement endpoint,
or when the remaining text no longer covers the fact value -- those rows are
recorded as kept with the reason. Syntax defects are out of scope for this round.

Outputs: a revision table (one record per changed pair, with fact and reason) and
three revised pool files. The original pool files are read-only here.
"""
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]
POOLS = (('verbalizer', WORKTREE / 'experiments/world-components/n4_narrative_dev/verbalizer_pairs.jsonl'),
         ('expand78', WORKTREE / 'artifacts/next-inputs/world-components/n4-expand78-unified.jsonl'),
         ('object34', WORKTREE / 'artifacts/next-inputs/world-components/n4-object34-unified.jsonl'))
ALIASES = {'潮汐档案馆': ['档案馆'], '潮渡': ['渡口', '栈桥'], '旧灯塔': ['灯塔'], '雾堤': ['堤面', '堤上'],
           '潮生巷': ['巷子'], '早市': ['集市']}
PUNCT = re.compile(r'[\s，,。．.；;：:！!？?、…—－\-\'"“”‘’（）()《》「」]')

# Curated deletions for outcome/appearance targets, keyed by the original target
# so duplicate rows stay consistent. Each entry: (reason, revised target).
CURATED = {
    '沈砚换好备用灯芯，火苗重新站稳。': ('T3', '沈砚换好备用灯芯。'),
    '阿棠把一叠干纸放在桌角，纸角被风掀起。': ('T2', '阿棠把一叠干纸放在桌角。'),
    '阿棠把一筐银鳞鱼搬上案板，鱼尾拍得筐沿响。': ('T1', '阿棠把一筐银鳞鱼搬上案板。'),
    '叶知微把玻璃罩上的盐雾擦掉，灯罩透亮起来。': ('T3', '叶知微把玻璃罩上的盐雾擦掉。'),
    '沈砚把潮汐簿缺的那页补全，合上了簿子。': ('T1', '沈砚把潮汐簿缺的那页补全。'),
    '韩渡把松脱的钟绳重新系紧，钟绳绷直了。': ('T3', '韩渡把松脱的钟绳重新系紧。'),
    '沈砚扶正警示灯，玻璃罩里的火苗晃了两下。': ('T2', '沈砚扶正警示灯。'),
    '沈砚把潮汐簿缺的那页补全，指尖沾了墨。': ('T2', '沈砚把潮汐簿缺的那页补全。'),
    '沈砚在潮渡等到最后一班船，船灯从雾里透出来。': ('T2', '沈砚在潮渡等到最后一班船。'),
    '沈砚换好了塔顶的灯芯，铜灯罩不再发暗。': ('T3', '沈砚换好了塔顶的灯芯。'),
    '沈砚在潮渡等到了最后一班渡船，船灯从雾里透出来。': ('T2', '沈砚在潮渡等到了最后一班渡船。'),
    '沈砚把系泊绳从浅滩拖回来，外袍下摆沾满泥水。': ('T2', '沈砚把系泊绳从浅滩拖回来。'),
    '沈砚换好了塔顶的灯芯，退开半步看火苗。': ('T1', '沈砚换好了塔顶的灯芯。'),
    '沈砚在潮渡等到了最后一班船，才向前走了一步。': ('T1', '沈砚在潮渡等到了最后一班船。'),
    '沈砚把系泊绳从浅滩拖了回来，绳子还在滴水。': ('T2', '沈砚把系泊绳从浅滩拖了回来。'),
    '叶知微把灯罩擦得透亮，玻璃上不再有雾。': ('T3', '叶知微把灯罩擦得透亮。'),
    '阿棠把干纸放到桌角，又伸手按住。': ('T1', '阿棠把干纸放到桌角。'),
    '韩渡把松脱的钟绳重新系紧，手背上沾着盐沫。': ('T2', '韩渡把松脱的钟绳重新系紧。'),
    '阿棠把银鳞鱼搬上案板，水花溅到石板上。': ('T2', '阿棠把银鳞鱼搬上案板。'),
    '阿棠把一叠干纸放在桌角，纸页还带着潮气。': ('T2', '阿棠把一叠干纸放在桌角。'),
    '沈砚的外袍下摆沾满泥水，边角结了一圈白盐。': ('T2', '沈砚的外袍下摆沾满泥水。'),
    '沈砚的指尖沾了墨，在纸边蹭了蹭。': ('T1', '沈砚的指尖沾了墨。'),
    '沈砚的外袍下摆被雾水打湿，贴在腿上。': ('T3', '沈砚的外袍下摆被雾水打湿。'),
    '叶知微的袖口沾了铜油，在灯影里发亮。': ('T3', '叶知微的袖口沾了铜油。'),
    '阿棠的鞋底带着早市的泥水，在门槛上蹭了两下。': ('T1', '阿棠的鞋底带着早市的泥水。'),
    '阿棠的辫梢沾了白汽，发梢微微发潮。': ('T3', '阿棠的辫梢沾了白汽。'),
    '沈砚的外袍下摆被海风掀起，衣角拍在腿上。': ('T3', '沈砚的外袍下摆被海风掀起。'),
    '沈砚的袖口被河风打湿，贴在手腕上。': ('T3', '沈砚的袖口被河风打湿。'),
    '沈砚的衣摆沾了泥水，边角沉甸甸地垂着。': ('T3', '沈砚的衣摆沾了泥水。'),
    '沈砚的鞋底沾了湿石板的水，在身后留下浅印。': ('T1', '沈砚的鞋底沾了湿石板的水。'),
}
KEPT_RISKY = {
    '沈砚一下一下拉动钟绳，雾警钟的声音撞进雾里。': '删除尾句后“敲响”只剩拉动动作，结果表达不完整',
}


def normalize(text):
    return PUNCT.sub('', text or '')


def bigrams(text):
    flat = normalize(text)
    return {flat[i:i + 2] for i in range(len(flat) - 1)}


def coverage(key, text):
    key_grams = bigrams(key)
    return len(key_grams & bigrams(text)) / len(key_grams) if key_grams else 1.0


def split_clauses(text):
    return [part for part in re.split(r'[，,]', text.rstrip('。')) if part.strip()]


def carries(text, place):
    return bool(place) and (place in text or any(alias in text for alias in ALIASES.get(place, [])))


def fact_of(row):
    match = re.search(r'事实=([^\n]*)', row['input'])
    return match.group(1).strip() if match else ''


def subject_value(row):
    parts = fact_of(row).split('｜')
    if len(parts) < 3:
        return None, None
    if row['kind'] == 'moved' and '→' in parts[2]:
        return parts[0], None
    return parts[0], parts[2]


def revise_moved(row):
    parts = fact_of(row).split('｜')
    if len(parts) < 3 or '→' not in parts[2]:
        return None
    start, destination = parts[2].split('→', 1)
    subject = parts[0]
    clauses = split_clauses(row['target'])
    if len(clauses) < 2:
        return None
    kept = [clauses[0]] + [c for c in clauses[1:] if carries(c, start) or carries(c, destination)]
    dropped = [c for c in clauses[1:] if c not in kept]
    if not dropped:
        return None
    revised = '，'.join(kept) + '。'
    if not carries(row['target'], start):
        return {'action': 'keep', 'reason': 'M0',
                'why': '原目标没写起点，删除尾句也补不回来（需改写，超出删除范围）'}
    if not carries(row['target'], destination):
        return {'action': 'keep', 'reason': 'M0',
                'why': '原目标没写终点，删除尾句也补不回来（需改写，超出删除范围）'}
    if subject not in revised:
        return {'action': 'keep', 'reason': 'M0', 'why': '删除后主体丢失'}
    return {'action': 'revise', 'reason': 'T1', 'revised': revised, 'dropped': dropped}


def main():
    table, revised_pools, counts = [], {}, {'changed': 0, 'kept': 0}
    for name, path in POOLS:
        rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
        out_rows = []
        for row in rows:
            original = row['target']
            record = None
            if row['kind'] == 'moved':
                record = revise_moved(row)
            if record is None and original in CURATED:
                reason, revised = CURATED[original]
                record = {'action': 'revise', 'reason': reason, 'revised': revised,
                          'dropped': [c for c in split_clauses(original) if c not in split_clauses(revised)]}
            if record is None and original in KEPT_RISKY:
                record = {'action': 'keep', 'reason': 'M0', 'why': KEPT_RISKY[original]}
            if record is None:
                out_rows.append(row)
                continue
            subject, value = subject_value(row)
            entry = {'pool': name, 'id': row.get('pairId') or row.get('unitId'),
                     'kind': row['kind'], 'fact': fact_of(row),
                     'original': original, 'action': record['action'],
                     'reason': record['reason']}
            if record['action'] == 'revise':
                revised = record['revised']
                entry['revised'] = revised
                entry['deleted'] = record['dropped']
                entry['why'] = {'T1': '移动之后追加了事实之外的动作或状态',
                                'T2': '追加了另一条事实',
                                'T3': '尾句重复了同一个结果'}[record['reason']]
                new_row = dict(row, target=revised)
                # the revision must still carry the subject and the fact value
                refusal = None
                if subject and subject not in revised:
                    refusal = '删除后主体丢失'
                elif row['kind'] == 'moved':
                    start, destination = fact_of(row).split('｜')[2].split('→', 1)
                    if not (carries(revised, start) and carries(revised, destination)):
                        refusal = '删除后起点或终点丢失'
                elif value and coverage(value, revised) + 1e-9 < coverage(value, original):
                    refusal = '删除后结果值覆盖率下降'
                if refusal:
                    # The fact would suffer, so the row stays as it is and is recorded.
                    entry.update(action='keep', reason='M0', why=refusal)
                    del entry['revised']
                    del entry['deleted']
                    out_rows.append(row)
                    counts['kept'] += 1
                    table.append(entry)
                    continue
                out_rows.append(new_row)
                counts['changed'] += 1
            else:
                entry['why'] = record['why']
                out_rows.append(row)
                counts['kept'] += 1
            table.append(entry)
        revised_pools[name] = out_rows

    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else WORKTREE / 'artifacts/next-runs/target-revision-r1'
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name, rows in revised_pools.items():
        path = target / f'{name}-revised.jsonl'
        text = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows)
        path.write_text(text, encoding='utf-8', newline='\n')
        files[name] = {'path': path.name, 'rows': len(rows),
                       'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'original': str(POOLS[[p[0] for p in POOLS].index(name)][1].relative_to(WORKTREE)),
                       'originalSha256': hashlib.sha256(POOLS[[p[0] for p in POOLS].index(name)][1].read_bytes()).hexdigest()}
    report = {'purpose': 'training-target revision r1: unsupported details and restatements only',
              'scope': 'moved tails carrying neither endpoint; trailing clauses stating another fact; '
                       'trailing clauses restating the result',
              'outOfScope': 'syntax defects (two-level 的, 的里面, possessive mismatch)',
              'counts': {'tableRows': len(table), **counts},
              'reasonCounts': {code: sum(1 for e in table if e['reason'] == code and e['action'] == 'revise')
                               for code in ('T1', 'T2', 'T3')},
              'pools': files, 'table': table}
    (target / 'revision-r1.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n',
                                             encoding='utf-8', newline='\n')
    print(json.dumps({k: report[k] for k in ('counts', 'reasonCounts')}, ensure_ascii=False))
    print('->', target / 'revision-r1.json')


if __name__ == '__main__':
    main()
