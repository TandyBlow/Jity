"""B 臂：在冻结的 A1 上做 v2 组织改写，输出正文 + 操作账本。

不训练、不改 u240、不接服务。输入是 artifacts/cohesion-split/a1.jsonl
（20 源，人工纠错条件）；模型是 qwen2.5:7b（本机 ollama，温度 0，JSON 模式）。

用法：
  python -X utf8 run_organize_v2.py --limit 1
  python -X utf8 run_organize_v2.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import time
import urllib.request

import sys as _paths_sys
_paths_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from component_paths import PATHS

ROOT = PATHS.worktree
A1 = PATHS.input('cohesion-split/a1.jsonl')
A1_FREEZE = PATHS.input('cohesion-split/a1-freeze.json')
CRITERIA = PATHS.input('cohesion-split/v2-criteria-freeze.json')
OUT = PATHS.output('cohesion-split/organize-v2-results.jsonl')
SUMMARY = PATHS.output('cohesion-split/organize-v2-summary.json')

OLLAMA = 'http://127.0.0.1:11434/api/generate'
MODEL = 'qwen2.5:7b'
ALLOWED = {'bg/1', 'coord/1', 'ref/1', 'seg/1', 'recast/1'}
TIME_WORDS = ['同时', '与此同时', '然后', '接着', '之后', '片刻后', '不久',
              '过了一会儿', '各忙各的', '这时', '一边']
PROMPT_VERSION = 'organize-v2-prompt/1'


def load_jsonl(path: pathlib.Path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()
            if line.strip()]


def atoms_of(scene: str):
    return [a.strip() for a in (scene or '').split('；') if a.strip()]


def relation_rows(relations):
    rows = []
    for i, pair in enumerate(relations or []):
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            rows.append({'id': f'r{i}', 'from': pair[0], 'to': pair[1]})
    return rows


def prompt_for(row):
    facts = row['facts']
    fact_lines = []
    for f in facts:
        text = f.get('factText')
        if text is None:
            text = f.get('u240') or '无变化'
        fact_lines.append(f"{f.get('factId')}｜{f.get('name')}｜{f.get('kind')}｜{text}")
    rel = relation_rows(row.get('relations'))
    rel_text = '；'.join(f"{r['id']}: {r['from']}->{r['to']}（before, pass）" for r in rel) or '无'
    endpoint_ids = sorted({x for r in rel for x in (r['from'], r['to'])})
    endpoint_names = []
    for fid in endpoint_ids:
        name = next((f.get('name') for f in facts if f.get('factId') == fid), None)
        if name:
            endpoint_names.append(f'{fid}={name}')
    endpoint_text = '、'.join(endpoint_ids) + ('（' + '、'.join(endpoint_names) + '）' if endpoint_names else '') if endpoint_ids else '无'
    relation_target_names = {}
    for r in rel:
        name = next((f.get('name') for f in facts if f.get('factId') == r['to']), None)
        if name:
            relation_target_names[r['id']] = name
    scene_atoms = atoms_of(row.get('scene'))
    return f"""你是叙事组织器。输入是一段已经过人工纠错的短句 A1、权威事实和授权背景。只做组织，不改事实。

允许的操作（op 只能取这些）：
- bg/1 背景穿插：把场景原子或地点名放在段首/句首/两个事实块之间/段尾；不得加人物、新事件、状态变化、时间关系、人物位置。
- coord/1 跨主体并列：相邻两条异主体事实用“，”或“；”并成一句；两个主体名都保留；不用同时/然后/接着/之后/片刻后；用“也/都”时必须保持两个原有断言的主体、对象、否定、模态、取值；“都”的范围只含明确列出的对象。
- ref/1 指代：把重复姓名换成“他/她”，或补回零主语；只有全段同性别/同数人物唯一且紧邻前一个主语时才能用。
- seg/1 断句：改标点、拆句；不改事实顺序；不跨关系端点；不留无主语残句。
- recast/1 单事实内改写：同一条事实内改“把”字句、调对象/动词位置、加逗号；不改主体、对象、结果、方向、否定、数量、时态、顺序。

禁止：
- 事实重排；新增人物/物件/动作/感官/事件/因果/目的/时间关系；同时/各忙各的；人物在具体物件下/旁；没有完整授权的带谓词背景。
- 关系端点的句界和方向不能动；A1 里已有的“随后”不能移动或重复；A1 中已有的句子不得删除，只能做上述五种操作。

背景（只能用这些）：
地点={row.get('place')}
场景原子={'、'.join(scene_atoms)}
可见={'、'.join((row.get('visible') or '').split('、'))}
可见只授权物件存在，不授权状态/位置。名词短语的每个原子都要有依据；“着/里”按完整表达判断，不按词表放行。
背景是可选的：如果当前场景原子能让段落更清楚，可以用 bg/1 放在段首/句首；不要为了用而用。

事实（按顺序；factId｜主体｜种类｜内容）：
{chr(10).join(fact_lines)}

关系：{rel_text}
端点：{endpoint_text}；端点句界不能合并/拆分；“随后”后必须以关系目标的姓名开头（{relation_target_names or '无'}）。

A1：
{row['A1']}

输出 JSON，不要解释。schema：
{{"text":"最终正文","operations":[{{"op":"<操作ID>","source":"<A1 中被改的原文；插入操作可为空>","target":"<新文片段>","factIds":["<factId>"],"atoms":["<场景原子或地点名>"],"relationIds":["<关系ID>"],"note":"<可选，短>"}}]}}
operations 只记实际做过的组织操作；没有操作就输出空数组。factIds/atoms/relationIds 只填上面出现过的 ID。
"""


def call_ollama(prompt):
    body = json.dumps({
        'model': MODEL,
        'prompt': prompt,
        'stream': False,
        'format': 'json',
        'options': {'temperature': 0, 'num_predict': 900, 'num_ctx': 4096},
    }, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(OLLAMA, data=body,
                                     headers={'content-type': 'application/json'})
    started = time.perf_counter()
    payload = json.load(urllib.request.urlopen(request, timeout=900))
    return {
        'raw': payload.get('response') or '',
        'seconds': round(time.perf_counter() - started, 2),
        'evalCount': payload.get('eval_count'),
        'promptEvalCount': payload.get('prompt_eval_count'),
    }


def parse_json(raw):
    try:
        return json.loads(raw), None
    except Exception as exc:
        # 取第一个平衡的 {...}，只作为一次补救，不改变模型输出
        start = raw.find('{')
        if start != -1:
            depth = 0
            for i in range(start, len(raw)):
                if raw[i] == '{':
                    depth += 1
                elif raw[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(raw[start:i + 1]), None
                        except Exception:
                            break
        return None, f'{type(exc).__name__}: {exc}'


def plain(text):
    return re.sub(r"[\s，,。．.；;：:！!？?、…—－\-'\"“”‘’（）()《》「」]", '', text or '')


def content_bigrams(text):
    text = plain(text)
    return {text[i:i + 2] for i in range(len(text) - 1)}


def check(row, parsed):
    flags = []
    text = (parsed.get('text') or '').strip() if isinstance(parsed, dict) else ''
    ops = parsed.get('operations') if isinstance(parsed, dict) else None
    if not text:
        flags.append('empty-text')
    if not isinstance(ops, list):
        flags.append('operations-not-list')
        ops = []
    facts = row['facts']
    fact_ids = {f.get('factId') for f in facts}
    fact_order = {f.get('factId'): i for i, f in enumerate(facts)}
    scene_atoms = atoms_of(row.get('scene'))
    visible_atoms = [a for a in (row.get('visible') or '').split('、') if a]
    allowed_atoms = set(scene_atoms) | set(visible_atoms) | {row.get('place')}
    relations = relation_rows(row.get('relations'))
    relation_ids = {r['id'] for r in relations}
    endpoints = {r['from'] for r in relations} | {r['to'] for r in relations}

    for word in TIME_WORDS:
        if word in text:
            flags.append(f'time-word:{word}')

    names = {f.get('factId'): f.get('name') for f in facts}
    for op in ops:
        if not isinstance(op, dict):
            flags.append('op-not-object')
            continue
        if not op:
            flags.append('empty-op')
            continue
        name = op.get('op')
        if name not in ALLOWED:
            flags.append(f'op-not-allowed:{name}')
        fids = op.get('factIds') or []
        if not isinstance(fids, list):
            flags.append('factIds-not-list')
            fids = []
        fids = [fid for fid in fids if isinstance(fid, str)]
        for fid in fids:
            if fid not in fact_ids:
                flags.append(f'unknown-fact:{fid}')
        idxs = [fact_order[fid] for fid in fids if fid in fact_order]
        if idxs != sorted(idxs):
            flags.append('op-fact-order')
        if name == 'coord/1':
            if len(fids) < 2:
                flags.append('coord-fewer-than-two')
            if idxs and idxs != list(range(min(idxs), max(idxs) + 1)):
                flags.append('coord-not-contiguous')
            op_names = [names.get(fid) for fid in fids]
            if all(op_names) and len(set(op_names)) == 1:
                flags.append('coord-same-subject')
            if any(n is None for n in op_names):
                flags.append('coord-subject-unknown')
        if name == 'recast/1' and len(fids) > 1:
            flags.append('recast-multi-fact')
        if name == 'ref/1' and len(fids) != 1:
            flags.append('ref-fact-count')
        atoms = op.get('atoms') or []
        for atom in atoms:
            if atom not in allowed_atoms:
                flags.append(f'unknown-atom:{atom}')
            elif atom in visible_atoms and atom not in scene_atoms and atom != row.get('place'):
                flags.append(f'visible-atom:{atom}')
        for rid in (op.get('relationIds') or []):
            if rid not in relation_ids:
                flags.append(f'unknown-relation:{rid}')
        if name == 'coord/1' and (set(fids) & endpoints):
            flags.append('endpoint-in-coord')
        source = (op.get('source') or '').strip()
        target = (op.get('target') or '').strip()
        if source and source not in row['A1']:
            flags.append('source-not-in-A1')
        if target and target not in text:
            flags.append('target-not-in-text')
        # op 声明的 factIds 与 source 覆盖对不上：漏报/多报
        src_plain = plain(source)
        for f in facts:
            fid = f.get('factId')
            ft = f.get('factText')
            key = plain(ft) if ft and ft != 'None→None' else plain(f.get('u240') or '')
            if not key:
                continue
            in_src = key in src_plain
            if in_src and fid not in fids:
                flags.append(f'op-missing-fact:{fid}')
            if fid in fids and not in_src:
                flags.append(f'op-extra-fact:{fid}')

    # 事实覆盖/顺序：只用内容二元组做粗检，标 review，不判死
    positions = []
    for f in facts:
        ft = f.get('factText')
        if not ft or '→' in ft:
            continue
        grams = content_bigrams(ft)
        if not grams:
            continue
        pos = min((text.find(g) for g in grams if text.find(g) >= 0), default=-1)
        if pos < 0:
            flags.append(f'fact-not-found:{f.get("factId")}')
        else:
            positions.append((fact_order[f['factId']], pos))
    for (a_i, a_p), (b_i, b_p) in zip(positions, positions[1:]):
        if a_i < b_i and a_p > b_p:
            flags.append('text-order-review')
            break

    # 新句号/分号后不能是“把/被/将”开头的无主残句
    for clause in re.split(r'[；。]', text)[1:]:
        clause = clause.strip()
        if clause.startswith(('把', '被', '将')):
            if not any(clause.startswith(n) for n in names.values() if n) and not clause.startswith(('他', '她')):
                flags.append('subjectless-clause')

    # 关系目标“随后”后是否仍以姓名开头
    for r in relations:
        target_name = next((f.get('name') for f in facts if f.get('factId') == r['to']), None)
        if target_name and '随后' in text:
            pos = text.find('随后')
            tail = text[pos + len('随后'):].lstrip('，, ')
            if tail and not tail.startswith(target_name):
                flags.append('connector-target-name')
    return flags


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--source', default=None)
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args()

    rows = load_jsonl(A1)
    if args.source:
        rows = [r for r in rows if r['sourceId'] == args.source]
        if not rows:
            raise SystemExit(f'unknown source: {args.source}')
    if args.limit:
        rows = rows[:args.limit]
    freeze = json.loads(A1_FREEZE.read_text(encoding='utf-8'))
    criteria = json.loads(CRITERIA.read_text(encoding='utf-8'))
    prompt_hash = hashlib.sha256(PROMPT_VERSION.encode('utf-8')).hexdigest()
    out_path = PATHS.output(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    results = []
    for i, row in enumerate(rows, 1):
        prompt = prompt_for(row)
        call = call_ollama(prompt)
        parsed, parse_error = parse_json(call['raw'])
        flags = check(row, parsed) if parsed else ['parse-failed']
        result = {
            'sourceId': row['sourceId'],
            'model': MODEL,
            'promptVersion': PROMPT_VERSION,
            'promptHash': prompt_hash,
            'prompt': prompt,
            'raw': call['raw'],
            'parsed': parsed,
            'parseError': parse_error,
            'seconds': call['seconds'],
            'evalCount': call['evalCount'],
            'promptEvalCount': call['promptEvalCount'],
            'checks': flags,
        }
        results.append(result)
        with out_path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(result, ensure_ascii=False) + '\n')
        print(f"[{i}/{len(rows)}] {row['sourceId']} {call['seconds']}s "
              f"parse={'ok' if parsed else 'fail'} flags={len(flags)}", flush=True)

    op_counts = {}
    for r in results:
        for op in ((r.get('parsed') or {}).get('operations') or []):
            name = op.get('op') if isinstance(op, dict) else '?'
            op_counts[name] = op_counts.get(name, 0) + 1
    summary = {
        'model': MODEL,
        'promptVersion': PROMPT_VERSION,
        'promptHash': prompt_hash,
        'a1Sha256': freeze['a1Sha256'],
        'criteriaSha256': hashlib.sha256(CRITERIA.read_bytes()).hexdigest(),
        'contractSha256': criteria.get('contractSha256'),
        'sourceCount': len(results),
        'parseOk': sum(1 for r in results if r.get('parsed')),
        'parseFail': sum(1 for r in results if not r.get('parsed')),
        'totalSeconds': round(time.perf_counter() - started, 2),
        'meanSeconds': round(sum(r['seconds'] for r in results) / max(len(results), 1), 2),
        'opCounts': op_counts,
        'flagCounts': {},
    }
    for r in results:
        for f in r['checks']:
            summary['flagCounts'][f] = summary['flagCounts'].get(f, 0) + 1
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
