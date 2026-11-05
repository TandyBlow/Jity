"""独立语义纠错 C：只删语义复述和未经支持的附加陈述。

输入：A0（u240 原稿）、逐事实权威内容、场景/可见授权。
输出：keep，或 A0 中的精确删除片段；程序只执行删除，不安全则 pending/A0。
不训练、不改 A1、不改服务。
"""
from __future__ import annotations

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
OUT = PATHS.output('cohesion-split/semantic-correct-results.jsonl')
SUMMARY = PATHS.output('cohesion-split/semantic-correct-summary.json')

OLLAMA = 'http://127.0.0.1:11434/api/generate'
MODEL = 'qwen2.5:7b'
PROMPT_VERSION = 'semantic-correct/1'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def plain(text):
    return re.sub(r"[\s，,。．.；;：:！!？?、…—－\-'\"“”‘’（）()《》「」]", '', text or '')


def grams(text):
    t = plain(text)
    return {t[i:i + 2] for i in range(len(t) - 1)}


def prompt_for(row):
    fact_lines = []
    for f in row['facts']:
        ft = f.get('factText')
        if ft in (None, 'None→None'):
            ft = '无变化（no_change）'
        fact_lines.append(
            f"{f.get('factId')}｜{f.get('name')}｜{f.get('kind')}｜权威内容：{ft}｜u240：{f.get('u240')}")
    return f"""你是语义纠错器。只做一件事：在 A0 里找“语义复述”和“未经支持的附加陈述”，给出要删除的原文精确片段。不要改写、不要补漏、不要修错对象、不要润色、不要组织。

来源：
源={row['sourceId']}
地点={row.get('place')}
场景={'；'.join(a.strip() for a in (row.get('scene') or '').split('；') if a.strip())}
可见={row.get('visible')}

A0（u240 原稿）：
{row['A0']}

逐事实（权威内容）：
{chr(10).join(fact_lines)}

规则：
1. 只删两类：
   - 语义复述：A0 里重复表达了某个已授权事实的内容（不要求字面完全相同，但必须是同一个意思）。
   - 未经支持的附加陈述：A0 里的动作、状态、对象、结果、方位、时间、因果，在事实、场景、可见物里都没有依据。
2. 可见物只授权“存在”，不授权它的动作、状态或位置。例：可见天窗，不等于“小雨落在天窗外”；可见铜灯，不等于“铜灯亮着”或“在铜灯下”。
3. 不要删合法的身体/状态描写：如果权威事实本身写了“指节发白 / 掌心出汗 / 脸色发白”，它是合法内容；只删重复的那一份。
4. 双项事实：如果权威事实本身是“衣领湿了，肩头也湿了”这种两项，两项都合法；不要把第二项当复述。
5. 不修错对象，不补遗漏，不润色，不组织，不换词。
6. 删除片段必须是 A0 的连续子串，包含要删的标点；不要输出改写后的正文。
7. 如果不确定，输出 keep；程序会把不安全的删除标为 pending 并保留原稿。

输出 JSON：
{{"decision":"keep"}}
或
{{"decision":"delete","deletions":[{{"span":"，指节发白","type":"repetition","factIds":["f1"],"basis":"f1 已经说了指节发白，这一处是复述"}}]}}
"""


def call(prompt):
    body = json.dumps({
        'model': MODEL,
        'prompt': prompt,
        'stream': False,
        'format': 'json',
        'options': {'temperature': 0, 'num_predict': 700, 'num_ctx': 4096},
    }, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(OLLAMA, data=body,
                                 headers={'content-type': 'application/json'})
    started = time.perf_counter()
    payload = json.load(urllib.request.urlopen(req, timeout=900))
    return {
        'raw': payload.get('response') or '',
        'seconds': round(time.perf_counter() - started, 2),
        'evalCount': payload.get('eval_count'),
    }


def parse_json(raw):
    try:
        return json.loads(raw), None
    except Exception as exc:
        return None, f'{type(exc).__name__}: {exc}'


def coverage(fact, text):
    ft = fact.get('factText')
    if ft in (None, 'None→None'):
        ft = fact.get('u240') or ''
    g = grams(ft)
    if not g:
        return 1.0
    return sum(1 for x in g if x in text) / len(g)


def check_and_apply(row, parsed):
    flags = []
    a0 = row['A0']
    if not isinstance(parsed, dict):
        return ['parse-failed'], 'invalid', a0, []
    decision = parsed.get('decision')
    if decision == 'keep':
        return [], 'keep', a0, []
    if decision != 'delete':
        return [f'invalid-decision:{decision}'], 'invalid', a0, []
    deletions = parsed.get('deletions')
    if not isinstance(deletions, list) or not deletions:
        return ['no-deletions'], 'invalid', a0, []
    spans = []
    for d in deletions:
        if not isinstance(d, dict):
            flags.append('deletion-not-object')
            continue
        span = d.get('span')
        typ = d.get('type')
        if not isinstance(span, str) or not span.strip():
            flags.append('empty-span')
            continue
        if typ not in ('repetition', 'unsupported'):
            flags.append(f'unknown-type:{typ}')
        start = a0.find(span)
        if start == -1:
            flags.append('span-not-found')
            continue
        if a0.find(span, start + 1) != -1:
            flags.append('ambiguous-span')
            continue
        spans.append((start, start + len(span), span, d))
    if flags:
        return flags, 'pending', a0, []
    # overlap check
    spans_sorted = sorted(spans, key=lambda x: x[0])
    for (a, b, _, _), (c, d, _, _) in zip(spans_sorted, spans_sorted[1:]):
        if c < b:
            flags.append('overlap-span')
    if flags:
        return flags, 'pending', a0, []
    out = a0
    for start, end, span, _ in sorted(spans, key=lambda x: x[0], reverse=True):
        out = out[:start] + out[end:]
    # 删除片段含句号、又不在 A0 末尾：可能把前一句和下一句拼在一起
    for start, end, span, _ in spans_sorted:
        if '。' in span and end < len(a0):
            before = a0[:start].rstrip()
            if not before.endswith(('。', '！', '？', '；')):
                flags.append('sentence-concatenation')
                break
    # punctuation / sentence checks
    bad = ['，，', '。。', '，。', '。，', '；。', '，；', '、。', '。、', '；；']
    for b in bad:
        if b in out:
            flags.append(f'broken-punctuation:{b}')
            break
    if out.strip().startswith(('，', '。', '；')):
        flags.append('leading-punctuation')
    if a0.rstrip().endswith('。') and not out.rstrip().endswith('。'):
        flags.append('missing-final-period')
    # mandatory fact coverage: only flag a drop from A0
    for f in row['facts']:
        before = coverage(f, a0)
        after = coverage(f, out)
        if before >= 0.6 and after < 0.6:
            flags.append(f'fact-coverage-drop:{f.get("factId")}')
        if '也' in (f.get('factText') or '') and after < 0.6:
            flags.append(f'double-item-risk:{f.get("factId")}')
    if flags:
        return flags, 'pending', a0, []
    applied = [{'span': s[2], 'type': s[3].get('type'),
                'factIds': s[3].get('factIds'), 'basis': s[3].get('basis')}
               for s in spans_sorted]
    return [], 'deleted', out, applied


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in A1.read_text(encoding='utf-8').splitlines() if l.strip()]
    freeze = load(A1_FREEZE)
    results = []
    started = time.perf_counter()
    for i, row in enumerate(rows, 1):
        prompt = prompt_for(row)
        callres = call(prompt)
        parsed, parse_error = parse_json(callres['raw'])
        flags, status, c_text, applied = check_and_apply(row, parsed)
        results.append({
            'sourceId': row['sourceId'],
            'A0': row['A0'],
            'A1': row['A1'],
            'facts': row['facts'],
            'place': row.get('place'),
            'scene': row.get('scene'),
            'visible': row.get('visible'),
            'prompt': prompt,
            'raw': callres['raw'],
            'parsed': parsed,
            'parseError': parse_error,
            'status': status,
            'proposed': (parsed or {}).get('deletions', []) if isinstance(parsed, dict) else [],
            'applied': applied,
            'C': c_text,
            'flags': flags,
            'seconds': callres['seconds'],
            'evalCount': callres['evalCount'],
        })
        print(f"[{i}/{len(rows)}] {row['sourceId']} {callres['seconds']}s "
              f"status={status} applied={len(applied)} flags={len(flags)}", flush=True)
    OUT.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in results) + '\n',
                   encoding='utf-8')
    summary = {
        'model': MODEL,
        'promptVersion': PROMPT_VERSION,
        'a1Sha256': freeze['a1Sha256'],
        'sourceCount': len(results),
        'parseOk': sum(1 for x in results if x['parsed']),
        'parseFail': sum(1 for x in results if not x['parsed']),
        'statusCounts': {},
        'proposedCount': sum(len(x['proposed']) for x in results),
        'appliedCount': sum(len(x['applied']) for x in results),
        'flagCounts': {},
        'totalSeconds': round(time.perf_counter() - started, 2),
        'meanSeconds': round(sum(x['seconds'] for x in results) / max(len(results), 1), 2),
    }
    for x in results:
        summary['statusCounts'][x['status']] = summary['statusCounts'].get(x['status'], 0) + 1
        for f in x['flags']:
            summary['flagCounts'][f] = summary['flagCounts'].get(f, 0) + 1
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
