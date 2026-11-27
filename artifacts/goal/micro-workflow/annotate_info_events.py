# -*- coding: utf-8 -*-
"""Independent information-event annotation (0..N items, four modes).

Labels do NOT come from the program rules. A strong model reads the action,
settled facts, narration and prior facts, and lists what the receiver actually
learned. Program checks only verify evidence spans, enum values and novelty
against prior text; they never choose the information."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from real_semantic_data import load_env, load_semantic_routes, settled, world_identity  # noqa: E402

OUT = HERE / 'semantic-info-events-v2.jsonl'
CACHE = HERE / 'info-events-cache.jsonl'
PROMPT_VERSION = 'info-v1'
MODES = {'specified', 'open', 'multi', 'inference'}
SOURCES = {'question', 'dialogue', 'observation', 'location', 'history', 'cross_event'}
QUESTION = re.compile('问|打听|询问|请教|什么|哪|谁|怎么|是否|有没有|多少|几|关于')


def text_hash(row):
    payload = '\n'.join([row.get('input') or '', ' '.join(str(item.get('text') or '') for item in row.get('settled') or []),
                         row.get('text') or '', (row.get('priorText') or '')[-2000:], PROMPT_VERSION])
    return hashlib.sha256(payload.encode('utf8')).hexdigest()


def prompt(row, name):
    facts = '\n'.join(str(item.get('text') or '') for item in row.get('settled') or [] if item.get('task') == 'results')
    prior = (row.get('priorText') or '')[-2000:]
    return f'''你是 Jity（中文 TRPG）的独立信息事件标注员。只依据下面的行动、结算事实、正文和此前事实，判断接收者（默认主角{name}）在本回合实际获得了哪些信息。
规则：
- 忽略结算事实里的结构化标记（环境=、去向=、信息=、涉及=），它们不是信息判断的依据。
- 一条信息项是接收者在本回合新知道的一个具体事实或结论，不是行动本身，也不是外观的罗列。
- 0 条是合法结果；不要为了凑数输出。
- mode 取值：specified（行动有明确问题或指定对象）｜open（无明确问题的观察）｜multi（本回合获得两条及以上）｜inference（结论需要结合此前事实）。
- source 取值：question（问答）｜dialogue（对话或转述）｜observation（看见听见的现象）｜location（地点环境）｜history（此前已有）｜cross_event（跨事件）。
- evidence：支持该信息项的原句，必须逐字来自下面给出的任一段落。
- novel：接收者此前不知道才为 true；此前事实里已有则为 false。
- 不确定就输出 abstain=true 与空 items，不要猜。
只输出一个 JSON：{{"abstain":false,"items":[{{"content":"…","mode":"specified|open|multi|inference","source":"question|dialogue|observation|location|history|cross_event","evidence":"…","novel":true}}]}}
玩家行动：{row.get('input') or ''}
结算事实：{facts[:1500]}
正文：{(row.get('text') or '')[:1200]}
此前事实（节选）：{prior}
'''


def parse(text):
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def verify(row, proposal):
    facts = ' '.join(str(item.get('text') or '') for item in row.get('settled') or [] if item.get('task') == 'results')
    narration = row.get('text') or ''
    prior = row.get('priorText') or ''
    corpus = facts + '\n' + narration + '\n' + prior
    items = []
    rejected = []
    if proposal.get('abstain'):
        return [], [{'reason': 'abstained'}]
    for raw in proposal.get('items') or []:
        content = str(raw.get('content') or '').strip()
        evidence = str(raw.get('evidence') or '').strip()
        mode = str(raw.get('mode') or '').strip()
        source = str(raw.get('source') or '').strip()
        novel = raw.get('novel')
        if not content or len(content) < 2:
            rejected.append({'content': content, 'reason': 'empty_content'})
            continue
        if evidence not in corpus:
            rejected.append({'content': content, 'reason': 'evidence_not_in_source'})
            continue
        if mode not in MODES or source not in SOURCES or not isinstance(novel, bool):
            rejected.append({'content': content, 'reason': 'enum_or_novel'})
            continue
        if mode == 'specified' and not QUESTION.search(row.get('input') or ''):
            rejected.append({'content': content, 'reason': 'specified_without_question'})
            continue
        if novel and content in prior:
            rejected.append({'content': content, 'reason': 'novel_but_in_prior'})
            continue
        if not novel and content not in prior:
            rejected.append({'content': content, 'reason': 'known_but_not_in_prior'})
            continue
        items.append({'content': content, 'mode': mode, 'source': source, 'evidence': evidence, 'novel': novel})
    if len(items) >= 2:
        for item in items:
            item['mode'] = 'multi'
    return items, rejected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    rows = [row for row in load_semantic_routes() if row.get('source') == 'semantic']
    if args.limit:
        rows = rows[:args.limit]
    _, name = world_identity()
    done = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding='utf8').splitlines():
            if line.strip():
                record = json.loads(line)
                done[(record.get('id'), record.get('inputHash'))] = record
    pending = [row for row in rows if (row['id'], text_hash(row)) not in done]
    print(f'{len(rows)} rows, {len(pending)} pending', flush=True)
    if pending:
        env = load_env()
        key = env.get('DEEPSEEK_API_KEY') or os.environ.get('DEEPSEEK_API_KEY', '')
        if not key:
            print('no api key', file=sys.stderr)
            sys.exit(1)
        from openai import OpenAI
        client = OpenAI(api_key=key, base_url=env.get('LLM_BASE_URL') or 'https://api.deepseek.com',
                        timeout=90, max_retries=2)
        model = os.environ.get('LABEL_MODEL') or env.get('LABEL_MODEL') or 'deepseek-chat'
        lock = threading.Lock()

        def work(row):
            try:
                response = client.chat.completions.create(
                    model=model, temperature=0,
                    messages=[{'role': 'user', 'content': prompt(row, name)}])
                proposal = parse(response.choices[0].message.content or '')
            except Exception as error:
                return row['id'], f'api-error:{str(error)[:100]}'
            if proposal is None:
                return row['id'], 'bad-json'
            record = {'id': row['id'], 'inputHash': text_hash(row), 'promptVersion': PROMPT_VERSION,
                      'labelModel': model, 'proposal': proposal, 'at': time.time()}
            with lock:
                with CACHE.open('a', encoding='utf8') as handle:
                    handle.write(json.dumps(record, ensure_ascii=False) + '\n')
                done[(row['id'], record['inputHash'])] = record
            return row['id'], 'ok'

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for identity, status in pool.map(work, pending):
                print(identity, status, flush=True)

    output = []
    stats = {'items': 0, 'turns_with_items': 0, 'abstain': 0, 'novel': 0, 'rejected': 0}
    modes = {}
    for row in rows:
        record = done.get((row['id'], text_hash(row)))
        if not record:
            continue
        items, rejected = verify(row, record.get('proposal') or {})
        stats['rejected'] += len(rejected)
        stats['items'] += len(items)
        stats['turns_with_items'] += int(bool(items))
        stats['abstain'] += int(not items)
        for item in items:
            stats['novel'] += int(item['novel'])
            modes[item['mode']] = modes.get(item['mode'], 0) + 1
        output.append({'id': row['id'], 'rowId': row['id'], 'split': row.get('split', 'train'),
                       'class': row.get('class'), 'action': row.get('input'), 'items': items,
                       'rejected': rejected, 'labelModel': record.get('labelModel')})
    OUT.write_text(''.join(json.dumps(entry, ensure_ascii=False) + '\n' for entry in output), encoding='utf8')
    print(json.dumps({'turns': len(output), 'stats': stats, 'modes': modes}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
