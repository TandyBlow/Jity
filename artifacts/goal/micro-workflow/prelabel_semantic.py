# -*- coding: utf-8 -*-
"""Prefill the label cache for semantic routes with a small thread pool.

The main pipeline stays sequential and cache-first; this only removes the
network wait from the critical path."""
import concurrent.futures
import json
import os
import re
import sys
import threading
import time

from real_semantic_data import (CACHE, PROMPT_VERSION, input_hash, load_env,
                                load_semantic_routes, prompt, state_diff)


def cache_keys():
    keys = set()
    if CACHE.exists():
        for line in CACHE.read_text(encoding='utf8').splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            keys.add((record.get('id'), record.get('inputHash')))
    return keys


def main():
    rows = load_semantic_routes()
    keys = cache_keys()
    pending = [row for row in rows if (row['id'], input_hash(row)) not in keys]
    print(f'{len(rows)} rows, {len(pending)} pending', flush=True)
    if not pending:
        return
    env = load_env()
    key = env.get('DEEPSEEK_API_KEY') or os.environ.get('DEEPSEEK_API_KEY', '')
    if not key:
        print('no api key', file=sys.stderr)
        sys.exit(1)
    from openai import OpenAI
    client = OpenAI(api_key=key, base_url=env.get('LLM_BASE_URL') or 'https://api.deepseek.com',
                    timeout=90, max_retries=2)
    model = os.environ.get('LABEL_MODEL') or env.get('LABEL_MODEL') or 'deepseek-v4-pro'
    lock = threading.Lock()

    def work(row):
        try:
            response = client.chat.completions.create(
                model=model, temperature=0,
                messages=[{'role': 'user', 'content': prompt(row, state_diff(row))}])
            text = response.choices[0].message.content or ''
            match = re.search(r'\{.*\}', text, re.S)
            if not match:
                return row['id'], 'bad-json'
            proposal = json.loads(match.group(0))
        except Exception as error:
            return row['id'], f'api-error:{str(error)[:120]}'
        record = {'id': row['id'], 'inputHash': input_hash(row), 'promptVersion': PROMPT_VERSION,
                  'labelModel': model,
                  'evidence': {'info': (proposal.get('info') or {}).get('evidence'),
                               'env': (proposal.get('env') or {}).get('evidence')},
                  'label': proposal, 'at': time.time()}
        with lock:
            with CACHE.open('a', encoding='utf8') as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + '\n')
        return row['id'], 'ok'

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for identity, status in pool.map(work, pending):
            print(identity, status, flush=True)


if __name__ == '__main__':
    main()
