"""Build statement-verification materials (materials + design only, no training).

Reuses the N5 row corpus, fact canonicalizer and source-group discipline, but
creates a NEW task: full unit text + numbered candidate + facts/scene/visible
authorization -> supported / unsupported / uncertain + source IDs.

No string locating, no deletion, no rewriting.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from collections import Counter, defaultdict

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(WC / 'n4_corpus'))
sys.path.insert(0, str(HERE))

from build_n5_pairs import fact_desc, group_sentence_spans  # noqa: E402

ROOT = pathlib.Path('D:/others/Jity')
OUT_DIR = ROOT / 'artifacts' / 'statement-verification'
PAIRS = OUT_DIR / 'pairs-v1.jsonl'
REGRESSION = OUT_DIR / 'regression-v1.jsonl'
FREEZE = OUT_DIR / 'split-freeze.json'
AUDIT = OUT_DIR / 'audit.json'
A1 = ROOT / 'artifacts' / 'cohesion-split' / 'a1.jsonl'

NAMES = ['祁岸', '苏禾', '陆行', '白棠', '顾临', '叶舟', '江晚', '程野',
         '许棠', '韩青', '温砚', '沈川', '林渡', '谢迟', '商陆', '闻溪',
         '裴照', '宋岚', '唐屿', '方序', '霍青', '罗川', '邵宁', '段禾',
         '薛亭', '柳岸', '周砚', '秦禾', '孟川', '贺宁', '陶野', '尹棠']
OBJECTS = ['麻绳', '木箱', '竹筐', '纸伞', '铜灯', '石阶', '缆绳', '门闩', '灯罩', '鱼筐']
ACTIONS = ['收紧', '搬起', '系紧', '扶正', '擦亮', '推开', '拖回', '挂好']
BODIES = ['指节发白', '掌心出汗', '脸色发白', '肩头落着灰', '手背蹭破皮', '袖口湿透']
BGS = ['浓雾', '细雨', '薄雾', '夜雾', '雨后']
BG_DISPLAY = {'浓雾': '浓雾里', '细雨': '细雨里', '薄雾': '薄雾里',
              '夜雾': '夜雾里', '雨后': '雨后'}
ITEMS = ['铜灯', '纸灯笼', '警示灯', '风灯']


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fact_in(f, idx):
    try:
        text = fact_desc(f)
    except Exception:
        text = f.get('factText')
        if not text or text == 'None→None':
            text = f.get('u240') or ''
    return {
        'sourceId': f'F{idx}',
        'factId': f.get('factId'),
        'kind': f.get('kind'),
        'name': f.get('name'),
        'factText': text,
    }


def n5_split(group, family):
    if family == 'v2-c-salt':
        return 'confirm'
    return 'dev' if int(sha(group)[:8], 16) % 5 == 0 else 'train'


def build_n5():
    train_rows = [json.loads(l) for l in
                  (HERE / 'corpus_v2' / 'train-v2.jsonl').read_text(encoding='utf-8').splitlines()
                  if l.strip()]
    confirm_rows = [json.loads(l) for l in
                    (HERE / 'corpus_v2' / 'holdout-v2.jsonl').read_text(encoding='utf-8').splitlines()
                    if l.strip()]
    groups = defaultdict(list)
    for row in train_rows + confirm_rows:
        groups[row['sourceGroupId']].append(row)
    out = []
    skipped = Counter()
    for group, rows in groups.items():
        row = rows[0]
        split = n5_split(group, row['familyId'])
        spans = group_sentence_spans(row)
        per_sentence = defaultdict(list)
        for fid, sent in spans:
            per_sentence[sent].append(fid)
        chosen = None
        for fid, sent in spans:
            if len(per_sentence[sent]) != 1:
                continue
            if sent not in row['text']:
                skipped['candidate-not-in-text'] += 1
                continue
            fact = next((f for f in row['facts'] if f.get('factId') == fid), None)
            if fact is None or fact.get('kind') == 'time':
                continue
            chosen = (fid, sent, fact)
            break
        if chosen is None:
            skipped['no-single-fact-sentence'] += 1
            continue
        fid, sent, fact = chosen
        # if another authorized fact expresses the same statement verbatim,
        # removing the chosen fact leaves the candidate supported; the
        # unsupported label would be invalid. Drop the whole pair.
        dup = any(o.get('factId') != fid and o.get('name') == fact.get('name')
                  and fact_desc(o) == fact_desc(fact) for o in row['facts'])
        if dup:
            skipped['duplicate-fact'] += 1
            continue
        facts = [fact_in(f, i + 1) for i, f in enumerate(row['facts'])]
        cand_idx = next(i for i, f in enumerate(row['facts']) if f.get('factId') == fid)
        cand_src = f'F{cand_idx + 1}'
        pair_id = f'n5:{row["rowId"]}:{fid}:auth'
        base = {
            'pairId': pair_id, 'sourceId': group, 'sourceGroupId': group,
            'split': split, 'origin': 'n5-derived', 'category': 'general',
            'pairMode': 'authorization', 'fullText': row['text'],
            'candidateId': 'C1', 'candidateText': sent,
            'scene': [], 'visible': [],
            'notes': f'N5 row {row["rowId"]}; one-fact sentence; authorization-removal pair.',
        }
        out.append({**base, 'exampleId': f'{pair_id}:sup', 'label': 'supported',
                    'facts': facts, 'goldSourceIds': [cand_src],
                    'sourceRole': 'support', 'removedFactId': None})
        out.append({**base, 'exampleId': f'{pair_id}:unsup', 'label': 'unsupported',
                    'facts': [f for f in facts if f['sourceId'] != cand_src],
                    'goldSourceIds': [], 'sourceRole': 'none',
                    'removedFactId': cand_src})
    return out, skipped


def split_for_auth(i):
    return 'train' if i < 3 else ('dev' if i < 5 else 'confirm')


def mk_fact(sid, kind, name, text):
    return {'sourceId': sid, 'factId': sid.lower(), 'kind': kind, 'name': name, 'factText': text}


def build_synthetic():
    out = []
    idx = 0
    for cat in ['body', 'background', 'visible-state', 'extra-action']:
        for i in range(6):
            name = NAMES[idx % len(NAMES)]
            obj = OBJECTS[idx % len(OBJECTS)]
            action = ACTIONS[idx % len(ACTIONS)]
            idx += 1
            split = split_for_auth(i)
            sid = f'syn-{cat}-auth-{i + 1}'
            pair = f'syn:{cat}:auth:{i + 1}'
            if cat == 'body':
                body = BODIES[i % len(BODIES)]
                other = BODIES[(i + 3) % len(BODIES)]
                full = f'{name}把{obj}{action}，{body}。'
                cand = body
                act_text = f'把{obj}{action}'
                sup_facts = [mk_fact('F1', 'appearance_changed', name, body),
                             mk_fact('F2', 'action', name, act_text)]
                uns_facts = [mk_fact('F1', 'appearance_changed', name, other),
                             mk_fact('F2', 'action', name, act_text)]
                sup_scene = uns_scene = [{'sourceId': 'S1', 'text': '夜'}]
                sup_vis = uns_vis = [{'sourceId': 'V1', 'text': obj}]
                gold_sup, gold_uns = ['F1'], ['F1']
            elif cat == 'background':
                atom = BGS[i % len(BGS)]
                disp = BG_DISPLAY[atom]
                full = f'{disp}，{name}把{obj}{action}。'
                cand = disp
                act_text = f'把{obj}{action}'
                sup_facts = uns_facts = [mk_fact('F1', 'action', name, act_text)]
                sup_scene = [{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': atom}]
                uns_scene = [{'sourceId': 'S1', 'text': '夜'}]
                sup_vis = uns_vis = [{'sourceId': 'V1', 'text': obj}]
                gold_sup, gold_uns = ['S2'], ['S1']
            elif cat == 'visible-state':
                item = ITEMS[i % len(ITEMS)]
                full = f'{item}已点亮，{name}把{obj}{action}。'
                cand = f'{item}已点亮'
                act_text = f'把{obj}{action}'
                sup_facts = uns_facts = [mk_fact('F1', 'action', name, act_text)]
                sup_scene = [{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': f'{item}已点亮'}]
                uns_scene = [{'sourceId': 'S1', 'text': '夜'}]
                sup_vis = uns_vis = [{'sourceId': 'V1', 'text': item}]
                gold_sup, gold_uns = ['S2'], ['V1']
            else:
                act = f'把{obj}{action}'
                other_act = f'把{obj}{ACTIONS[(i + 3) % len(ACTIONS)]}'
                full = f'{name}{act}。'
                cand = full
                sup_facts = [mk_fact('F1', 'action', name, act)]
                uns_facts = [mk_fact('F1', 'action', name, other_act)]
                sup_scene = uns_scene = [{'sourceId': 'S1', 'text': '夜'}]
                sup_vis = uns_vis = []
                gold_sup, gold_uns = ['F1'], ['F1']
            base = {
                'pairId': pair, 'sourceId': sid, 'sourceGroupId': sid, 'split': split,
                'origin': 'synthetic', 'category': cat, 'pairMode': 'authorization',
                'fullText': full, 'candidateId': 'C1', 'candidateText': cand,
                'notes': 'same full text and candidate; only the authorization changes.',
            }
            out.append({**base, 'exampleId': f'{pair}:sup', 'label': 'supported',
                        'facts': sup_facts, 'scene': sup_scene, 'visible': sup_vis,
                        'goldSourceIds': gold_sup, 'sourceRole': 'support'})
            out.append({**base, 'exampleId': f'{pair}:unsup', 'label': 'unsupported',
                        'facts': uns_facts, 'scene': uns_scene, 'visible': uns_vis,
                        'goldSourceIds': gold_uns, 'sourceRole': 'checked'})

    idx = 100
    for cat in ['body', 'background', 'visible-state', 'extra-action']:
        for split in ['train', 'dev', 'confirm']:
            name = NAMES[idx % len(NAMES)]
            obj = OBJECTS[idx % len(OBJECTS)]
            action = ACTIONS[idx % len(ACTIONS)]
            idx += 1
            sid = f'syn-{cat}-stmt-{split}'
            pair = f'syn:{cat}:stmt:{split}'
            if cat == 'body':
                ok, bad = BODIES[0], BODIES[1]
                full_ok = f'{name}把{obj}{action}，{ok}。'
                full_bad = f'{name}把{obj}{action}，{bad}。'
                act_text = f'把{obj}{action}'
                sup_facts = [mk_fact('F1', 'appearance_changed', name, ok),
                             mk_fact('F2', 'action', name, act_text)]
                sup_scene, sup_vis = [{'sourceId': 'S1', 'text': '夜'}], [{'sourceId': 'V1', 'text': obj}]
                gold = ['F1']
            elif cat == 'background':
                ok, bad = '浓雾里', '细雨里'
                full_ok = f'{ok}，{name}把{obj}{action}。'
                full_bad = f'{bad}，{name}把{obj}{action}。'
                act_text = f'把{obj}{action}'
                sup_facts = [mk_fact('F1', 'action', name, act_text)]
                sup_scene = [{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': '浓雾'}]
                sup_vis = [{'sourceId': 'V1', 'text': obj}]
                gold = ['S2']
            elif cat == 'visible-state':
                ok, bad = '铜灯亮着', '铜灯熄了'
                full_ok = f'{ok}，{name}把{obj}{action}。'
                full_bad = f'{bad}，{name}把{obj}{action}。'
                act_text = f'把{obj}{action}'
                sup_facts = [mk_fact('F1', 'action', name, act_text)]
                sup_scene = [{'sourceId': 'S1', 'text': '夜'}, {'sourceId': 'S2', 'text': '铜灯已点亮'}]
                sup_vis = [{'sourceId': 'V1', 'text': '铜灯'}]
                gold = ['S2']
            else:
                ok = f'把{obj}{action}'
                bad = f'把{obj}{ACTIONS[(idx + 2) % len(ACTIONS)]}'
                full_ok = f'{name}{ok}。'
                full_bad = f'{name}{bad}。'
                sup_facts = [mk_fact('F1', 'action', name, ok)]
                sup_scene, sup_vis = [{'sourceId': 'S1', 'text': '夜'}], []
                gold = ['F1']
            base = {
                'pairId': pair, 'sourceId': sid, 'sourceGroupId': sid, 'split': split,
                'origin': 'synthetic', 'category': cat, 'pairMode': 'statement',
                'facts': sup_facts, 'scene': sup_scene, 'visible': sup_vis,
                'notes': 'same authorization; only the candidate/full text changes.',
            }
            out.append({**base, 'exampleId': f'{pair}:sup', 'label': 'supported',
                        'fullText': full_ok, 'candidateId': 'C1', 'candidateText': ok,
                        'goldSourceIds': gold, 'sourceRole': 'support'})
            out.append({**base, 'exampleId': f'{pair}:unsup', 'label': 'unsupported',
                        'fullText': full_bad, 'candidateId': 'C1', 'candidateText': bad,
                        'goldSourceIds': gold, 'sourceRole': 'checked'})

    for split in ['train', 'dev', 'confirm']:
        name = NAMES[idx % len(NAMES)]
        obj = OBJECTS[idx % len(OBJECTS)]
        action = ACTIONS[idx % len(ACTIONS)]
        idx += 1
        sid = f'syn-uncertain-{split}'
        full = f'棚下散着光，{name}把{obj}{action}。'
        out.append({
            'exampleId': f'syn:uncertain:{split}', 'pairId': f'syn:uncertain:{split}',
            'sourceId': sid, 'sourceGroupId': sid, 'split': split,
            'origin': 'synthetic', 'category': 'uncertain', 'pairMode': 'none',
            'label': 'uncertain', 'fullText': full, 'candidateId': 'C1',
            'candidateText': '棚下散着光',
            'facts': [mk_fact('F1', 'action', name, f'把{obj}{action}')],
            'scene': [{'sourceId': 'S1', 'text': '清晨'},
                                     {'sourceId': 'S2', 'text': '薄雾'},
                                     {'sourceId': 'S3', 'text': '棚下散光'}],
            'visible': [{'sourceId': 'V1', 'text': obj}],
            'goldSourceIds': ['S3'], 'sourceRole': 'support',
            'notes': 'state expression with 着; scene atom 棚下散光; review/uncertain.',
        })
    return out


def build_regression():
    rows = [json.loads(l) for l in A1.read_text(encoding='utf-8').splitlines() if l.strip()]
    out = []
    for row in rows:
        facts = [fact_in(f, i + 1) for i, f in enumerate(row['facts'])]
        fid_to_src = {f.get('factId'): f'F{i + 1}' for i, f in enumerate(row['facts'])}
        scene = [{'sourceId': f'S{i + 1}', 'text': a.strip()}
                 for i, a in enumerate((row.get('scene') or '').split('；')) if a.strip()]
        visible = [{'sourceId': f'V{i + 1}', 'text': a.strip()}
                   for i, a in enumerate((row.get('visible') or '').split('、')) if a.strip()]
        base = {
            'sourceId': f'reg:{row["sourceId"]}', 'sourceGroupId': f'reg:{row["sourceId"]}',
            'split': 'regression', 'origin': 'regression-20',
            'pairMode': 'none', 'candidateId': 'C1',
            'facts': facts, 'scene': scene, 'visible': visible,
        }
        for j, c in enumerate(row.get('corrections') or []):
            if c.get('type') != 'drop-unsourced':
                continue
            span = c.get('removed') or c.get('span') or c.get('text')
            if not span or span not in row['A0']:
                continue
            out.append({**base, 'exampleId': f'reg:{row["sourceId"]}:unsup:{j}',
                        'pairId': f'reg:{row["sourceId"]}:unsup:{j}',
                        'label': 'unsupported', 'category': 'regression-unsupported',
                        'fullText': row['A0'], 'candidateText': span,
                        'goldSourceIds': [fid_to_src[c['factId']]] if c.get('factId') in fid_to_src else [],
                        'sourceRole': 'checked',
                        'notes': f'A1 {c.get("type")}: {c.get("reason", "")}'})
        # supported: one appearance fact that is still present in A1
        for f, fi in zip(row['facts'], range(1, len(row['facts']) + 1)):
            if f.get('kind') != 'appearance_changed':
                continue
            ft = f.get('factText')
            if ft and ft in row['A1']:
                out.append({**base, 'exampleId': f'reg:{row["sourceId"]}:sup:appearance',
                            'pairId': f'reg:{row["sourceId"]}:sup:appearance',
                            'label': 'supported', 'category': 'regression-supported',
                            'fullText': row['A1'], 'candidateText': ft,
                            'goldSourceIds': [fid_to_src[f['factId']]],
                            'sourceRole': 'support',
                            'notes': 'A1 retained appearance fact; legal reference, not training.'})
                break
    return out


def target_regression():
    rows = {r['sourceId']: r for r in
            (json.loads(l) for l in A1.read_text(encoding='utf-8').splitlines() if l.strip())}
    targets = {
        'train-r1': (
            '浓雾里，沈砚的袖口沾了雨，指节发白。顾行舟的斗篷下摆湿了一片。随后，叶知微的鞋底沾了泥。叶知微的袖口湿到肘部。',
            [('浓雾里', 'supported', ['S2'], 'support', 'background')]),
        'v02': (
            '清晨的薄雾还没散，棚下散着光。阿棠把银鳞鱼按大小分开，装进鱼筐。顾行舟把抹布拧干，手背上沾了鱼鳞。',
            [('清晨的薄雾', 'supported', ['S1', 'S2'], 'support', 'background'),
             ('清晨的薄雾还没散', 'unsupported', ['S2'], 'checked', 'background'),
             ('棚下散着光', 'uncertain', ['S3'], 'support', 'uncertain')]),
        't19': (
            '清晨的薄雾里，棚下散着光。阿棠的袖口沾了鱼鳞，沈砚的外袍下摆沾了泥水。阿棠把银鳞鱼装进鱼筐；沈砚把油纸伞收拢靠在摊棚边。',
            [('清晨的薄雾里', 'supported', ['S1', 'S2'], 'support', 'background'),
             ('棚下散着光', 'uncertain', ['S3'], 'support', 'uncertain')]),
        't01': (
            '小雨落在天窗外。沈砚在铜灯下把潮汐簿缺的那页补全，指尖沾了墨；他合上簿子，推到桌角。',
            [('小雨落在天窗外', 'unsupported', ['S2', 'V7'], 'checked', 'visible-state'),
             ('在铜灯下', 'unsupported', ['V2'], 'checked', 'visible-state')]),
        'v05': (
            '叶知微的袖口沾了铜油，沈砚的手背上也沾了铜油。叶知微把灯罩擦得透亮。塔顶的灯还亮着，什么也没有再发生。',
            [('沈砚的手背上也沾了铜油', 'supported', ['F2'], 'support', 'body')]),
    }
    out = []
    for sid, (full, cands) in targets.items():
        row = rows[sid]
        facts = [fact_in(f, i + 1) for i, f in enumerate(row['facts'])]
        fid_to_src = {f.get('factId'): f'F{i + 1}' for i, f in enumerate(row['facts'])}
        scene = [{'sourceId': f'S{i + 1}', 'text': a.strip()}
                 for i, a in enumerate((row.get('scene') or '').split('；')) if a.strip()]
        visible = [{'sourceId': f'V{i + 1}', 'text': a.strip()}
                   for i, a in enumerate((row.get('visible') or '').split('、')) if a.strip()]
        for j, (cand, label, gold, role, cat) in enumerate(cands):
            if cand not in full:
                raise AssertionError((sid, cand))
            out.append({
                'exampleId': f'reg-target:{sid}:{j}', 'pairId': f'reg-target:{sid}:{j}',
                'sourceId': f'reg:{sid}', 'sourceGroupId': f'reg:{sid}',
                'split': 'regression', 'origin': 'regression-target',
                'category': cat, 'pairMode': 'none', 'label': label,
                'fullText': full, 'candidateId': 'C1', 'candidateText': cand,
                'facts': facts, 'scene': scene, 'visible': visible,
                'goldSourceIds': gold, 'sourceRole': role,
                'notes': '5-case target draft used only as regression; not training.',
            })
    return out


def audit(rows, regression):
    issues = []
    by_split = Counter(r['split'] for r in rows)
    by_label = Counter((r['split'], r['label']) for r in rows)
    by_cat = Counter((r['split'], r['category']) for r in rows)
    by_origin = Counter((r['split'], r['origin']) for r in rows)
    source_splits = defaultdict(set)
    text_splits = defaultdict(set)
    for r in rows + regression:
        source_splits[r['sourceGroupId']].add(r['split'])
        text_splits[(r['fullText'], r['candidateText'])].add(r['split'])
        if r['candidateText'] not in r['fullText']:
            issues.append(f'candidate-not-in-text:{r["exampleId"]}')
        ids = {x['sourceId'] for x in r['facts']} | {x['sourceId'] for x in r['scene']} | {x['sourceId'] for x in r['visible']}
        for gid in r['goldSourceIds']:
            if gid not in ids:
                issues.append(f'gold-source-missing:{r["exampleId"]}:{gid}')
    for src, splits in source_splits.items():
        if len(splits) > 1:
            issues.append(f'source-cross-split:{src}:{sorted(splits)}')
    for key, splits in text_splits.items():
        if len(splits) > 1:
            issues.append(f'text-cross-split:{key[0][:30]}:{sorted(splits)}')
    pairs = defaultdict(list)
    for r in rows:
        pairs[r['pairId']].append(r)
    for pid, rs in pairs.items():
        if len(rs) == 1:
            if rs[0]['label'] != 'uncertain':
                issues.append(f'pair-incomplete:{pid}')
            continue
        if len({r['split'] for r in rs}) != 1:
            issues.append(f'pair-split:{pid}')
        if {r['label'] for r in rs} != {'supported', 'unsupported'}:
            issues.append(f'pair-labels:{pid}')
        if rs[0]['pairMode'] == 'authorization':
            if len({(r['fullText'], r['candidateText']) for r in rs}) != 1:
                issues.append(f'auth-pair-text-diff:{pid}')
            diff = [k for k in ('facts', 'scene', 'visible') if rs[0].get(k) != rs[1].get(k)]
            if len(diff) != 1:
                issues.append(f'auth-pair-diff-{diff}:{pid}')
        if rs[0]['pairMode'] == 'statement':
            if any(rs[0].get(k) != rs[1].get(k) for k in ('facts', 'scene', 'visible')):
                issues.append(f'stmt-pair-auth-diff:{pid}')
            if rs[0]['candidateText'] == rs[1]['candidateText']:
                issues.append(f'stmt-pair-same-candidate:{pid}')
            rests = [r['fullText'].replace(r['candidateText'], '', 1) for r in rs]
            if rests[0] != rests[1]:
                issues.append(f'stmt-pair-rest-diff:{pid}')

    def lens(rs):
        xs = [len(r['candidateText']) for r in rs]
        return {'n': len(xs), 'mean': round(sum(xs) / len(xs), 2) if xs else 0,
                'min': min(xs) if xs else 0, 'max': max(xs) if xs else 0}

    length = {f'{s}:{l}': lens([r for r in rows if r['split'] == s and r['label'] == l])
              for s in sorted({r['split'] for r in rows})
              for l in ('supported', 'unsupported', 'uncertain')}
    return {
        'counts': {'total': len(rows) + len(regression),
                   'trainDevConfirm': len(rows), 'regression': len(regression),
                   'bySplit': dict(by_split),
                   'byLabel': {f'{k[0]}:{k[1]}': v for k, v in by_label.items()},
                   'byCategory': {f'{k[0]}:{k[1]}': v for k, v in by_cat.items()},
                   'byOrigin': {f'{k[0]}:{k[1]}': v for k, v in by_origin.items()}},
        'length': length, 'issues': issues, 'issueCount': len(issues),
    }


def main():
    n5, skipped = build_n5()
    syn = build_synthetic()
    reg = build_regression() + target_regression()
    rows = n5 + syn
    rows.sort(key=lambda r: (r['split'], r['origin'], r['pairId'], r['exampleId']))
    # drop exact duplicate pairs by (full text, candidate); keep both labels
    by_pair = defaultdict(list)
    for r in rows:
        by_pair[r['pairId']].append(r)
    seen = set()
    deduped = []
    dropped = 0
    dropped_pairs = 0
    for pid in sorted(by_pair):
        rs = by_pair[pid]
        key = (rs[0]['fullText'], rs[0]['candidateText'])
        if key in seen:
            dropped += len(rs)
            dropped_pairs += 1
            continue
        seen.add(key)
        deduped.extend(rs)
    rows = deduped
    reg.sort(key=lambda r: r['exampleId'])
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PAIRS.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    REGRESSION.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in reg), encoding='utf-8')
    audit_res = audit(rows, reg)
    audit_res['n5Skipped'] = dict(skipped)
    audit_res['dedupDropped'] = dropped
    audit_res['dedupDroppedPairs'] = dropped_pairs
    audit_res['hashes'] = {
        'pairs-v1.jsonl': hashlib.sha256(PAIRS.read_bytes()).hexdigest(),
        'regression-v1.jsonl': hashlib.sha256(REGRESSION.read_bytes()).hexdigest(),
        'a1.jsonl': hashlib.sha256(A1.read_bytes()).hexdigest(),
    }
    AUDIT.write_text(json.dumps(audit_res, ensure_ascii=False, indent=2), encoding='utf-8')
    metric_path = OUT_DIR / 'metric-freeze.json'
    freeze = {
        'version': 'statement-verify-v1', 'created': '2026-11-04',
        'task': 'full text + numbered candidate + facts/scene/visible -> supported/unsupported/uncertain + source IDs',
        'splits': {
            'train': 'N5 A/B source groups hash ~80%; synthetic targeted train sources',
            'dev': 'N5 A/B source groups hash ~20%; synthetic targeted dev sources',
            'confirm': 'N5 family C source groups (66) + synthetic targeted confirm sources',
            'regression': '20 expression sources + A1; never train/dev/confirm',
        },
        'counts': audit_res['counts'], 'hashes': audit_res['hashes'],
        'auditIssueCount': audit_res['issueCount'],
        'auditSha256': hashlib.sha256(AUDIT.read_bytes()).hexdigest(),
        'metricFreeze': str(metric_path.relative_to(ROOT)).replace('', '/'),
        'metricFreezeSha256': (hashlib.sha256(metric_path.read_bytes()).hexdigest()
                               if metric_path.exists() else None),
    }
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(audit_res['counts'], ensure_ascii=False, indent=2))
    print('issues', audit_res['issueCount'])
    print(json.dumps(audit_res['issues'][:30], ensure_ascii=False, indent=1))
    print(json.dumps(audit_res['n5Skipped'], ensure_ascii=False))
    print(json.dumps(audit_res['length'], ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
