"""独立任务：授权背景的选择与落点。

只让模型选 backgroundId + slotId，或 none；正文由程序按固定模板装配。
不训练、不改 A1、不自报编辑账本。

用法：
  python -X utf8 run_background_select.py
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import time
import urllib.request

ROOT = pathlib.Path('D:/others/Jity')
CAND = ROOT / 'artifacts' / 'cohesion-split' / 'background-candidates.json'
A1_FREEZE = ROOT / 'artifacts' / 'cohesion-split' / 'a1-freeze.json'
OUT = ROOT / 'artifacts' / 'cohesion-split' / 'background-select-results.jsonl'
SUMMARY = ROOT / 'artifacts' / 'cohesion-split' / 'background-select-summary.json'

OLLAMA = 'http://127.0.0.1:11434/api/generate'
MODEL = 'qwen2.5:7b'
PROMPT_VERSION = 'background-select/1'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def prompt_for(row):
    sent_lines = '\n'.join(f'{i}. {s}' for i, s in enumerate(row['sentences'], 1))
    bg_lines = '\n'.join(
        f"{b['backgroundId']}｜{b['atom']}｜展示={b['display']}｜来源={b['source']}"
        for b in row['backgrounds'])
    slot_lines = '\n'.join(
        f"{s['slotId']}｜{s['description']}" for s in row['slots'])
    return f"""你是背景选择器。只做一件事：从给定的背景原子和候选位置中选一个，或不插入。不要写正文，不要改背景内容，不要自报编辑账本。

A1 句子：
{sent_lines}

背景原子（只能选这些；都来自当前场景）：
{bg_lines}

候选位置（只能选这些）：
{slot_lines}

规则：
- 只能输出一个 backgroundId + slotId，或明确选 none。
- 背景必须来自当前场景，不能跨场景引用。
- 不能插进“随后＋姓名”的内部；如果某个位置后面紧接“随后…”，背景放在“随后”之前。
- 如果 A1 已经表达了该背景、背景会重复、会添加人物/新事件/时间/因果/目的，或没有合适位置，选 none。
- 背景是可选的；不要为了插入而插入。
- 选完后程序会按固定模板装配：s0 是“展示，+ 第一句”，其他 slot 是“在句界插入独立背景句”。你不需要写正文。

只输出 JSON：
{{"decision":"insert","backgroundId":"b0","slotId":"s0"}}
或
{{"decision":"none","reason":"..."}}
"""


def call(prompt):
    body = json.dumps({
        'model': MODEL,
        'prompt': prompt,
        'stream': False,
        'format': 'json',
        'options': {'temperature': 0, 'num_predict': 300, 'num_ctx': 4096},
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


def assemble(a1, sentences, display, slot_id):
    if slot_id == 's0':
        return display + '，' + a1
    i = int(slot_id[1:])
    return ''.join(sentences[:i]) + display + '。' + ''.join(sentences[i:])


def simple_choice(row):
    for b in row['backgrounds']:
        if b.get('frameUsable'):
            return b, row['slots'][0]
    return None, None


def content_hit(atom, text):
    # 粗检：原子里的双字片段是否已在 A1 出现；单字原子查单字
    keys = [atom] if len(atom) == 1 else [atom[i:i + 2] for i in range(len(atom) - 1)]
    return [k for k in keys if k and k in text]


def check(row, parsed, choice, output):
    flags = []
    if not isinstance(parsed, dict):
        return ['parse-failed'], None
    decision = parsed.get('decision')
    if decision not in ('insert', 'none'):
        flags.append(f'invalid-decision:{decision}')
    if decision == 'none':
        if output != row['A1']:
            flags.append('none-output-not-A1')
        return flags, None
    bg_id = parsed.get('backgroundId')
    slot_id = parsed.get('slotId')
    bg = next((b for b in row['backgrounds'] if b['backgroundId'] == bg_id), None)
    slot = next((s for s in row['slots'] if s['slotId'] == slot_id), None)
    if bg is None:
        flags.append(f'unknown-background:{bg_id}')
    if slot is None:
        flags.append(f'unknown-slot:{slot_id}')
    if bg is None or slot is None:
        return flags, None
    expected = assemble(row['A1'], row['sentences'], bg['display'], slot['slotId'])
    if output != expected:
        flags.append('assembly-mismatch')
    hits = content_hit(bg['atom'], row['A1'])
    if hits:
        flags.append('background-hits-A1:' + ','.join(hits))
    if '着' in bg['display'] or '已' in bg['display']:
        flags.append('state-display')
    if slot['slotId'] == 's0' and bg['display'] in ('塔顶铜灯已点亮',):
        flags.append('awkward-prefix')
    return flags, {'backgroundId': bg_id, 'atom': bg['atom'], 'display': bg['display'],
                   'slotId': slot_id, 'mode': slot['mode']}


def main():
    rows = load(CAND)
    a1_freeze = load(A1_FREEZE)
    prompt_hash = hashlib.sha256(PROMPT_VERSION.encode('utf-8')).hexdigest()
    results = []
    started = time.perf_counter()
    for i, row in enumerate(rows, 1):
        prompt = prompt_for(row)
        callres = call(prompt)
        parsed, parse_error = parse_json(callres['raw'])
        simple_bg, simple_slot = simple_choice(row)
        simple_out = (assemble(row['A1'], row['sentences'], simple_bg['display'], simple_slot['slotId'])
                      if simple_bg else row['A1'])
        if parsed and parsed.get('decision') == 'insert':
            bg = next((b for b in row['backgrounds']
                       if b['backgroundId'] == parsed.get('backgroundId')), None)
            slot = next((s for s in row['slots']
                         if s['slotId'] == parsed.get('slotId')), None)
            model_out = (assemble(row['A1'], row['sentences'], bg['display'], slot['slotId'])
                         if bg and slot else row['A1'])
        else:
            model_out = row['A1']
        flags, chosen = check(row, parsed, None, model_out)
        results.append({
            'sourceId': row['sourceId'],
            'A1': row['A1'],
            'sentences': row['sentences'],
            'backgrounds': row['backgrounds'],
            'slots': row['slots'],
            'prompt': prompt,
            'raw': callres['raw'],
            'parsed': parsed,
            'parseError': parse_error,
            'decision': (parsed or {}).get('decision'),
            'chosen': chosen,
            'simple': ({'backgroundId': simple_bg['backgroundId'], 'atom': simple_bg['atom'],
                        'display': simple_bg['display'], 'slotId': simple_slot['slotId']}
                       if simple_bg else None),
            'A1Text': row['A1'],
            'SimpleText': simple_out,
            'ModelText': model_out,
            'flags': flags,
            'seconds': callres['seconds'],
            'evalCount': callres['evalCount'],
        })
        print(f"[{i}/{len(rows)}] {row['sourceId']} {callres['seconds']}s "
              f"decision={ (parsed or {}).get('decision') } flags={len(flags)}", flush=True)

    OUT.write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in results) + '\n',
                   encoding='utf-8')
    summary = {
        'model': MODEL,
        'promptVersion': PROMPT_VERSION,
        'promptVersionHash': prompt_hash,
        'a1Sha256': a1_freeze['a1Sha256'],
        'candidatesSha256': hashlib.sha256(CAND.read_bytes()).hexdigest(),
        'sourceCount': len(results),
        'parseOk': sum(1 for x in results if x['parsed']),
        'parseFail': sum(1 for x in results if not x['parsed']),
        'decisionCounts': {},
        'flagCounts': {},
        'totalSeconds': round(time.perf_counter() - started, 2),
        'meanSeconds': round(sum(x['seconds'] for x in results) / max(len(results), 1), 2),
        'sameAsSimple': sum(1 for x in results
                            if x['chosen'] and x['simple']
                            and x['chosen']['backgroundId'] == x['simple']['backgroundId']
                            and x['chosen']['slotId'] == x['simple']['slotId']),
    }
    for x in results:
        summary['decisionCounts'][x['decision'] or 'parse-fail'] = \
            summary['decisionCounts'].get(x['decision'] or 'parse-fail', 0) + 1
        for f in x['flags']:
            summary['flagCounts'][f] = summary['flagCounts'].get(f, 0) + 1
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
