#!/usr/bin/env python3
"""Build an independent narration holdout from product run records.

A pair qualifies only if its fact block (the exact model input after 事实：) does
not appear in the narration corpus or the 161-point development bundle. That
makes it unseen by E55-E60 rule design and by corpus-trained models. The set is
frozen with a canonical-JSON manifest; evaluate with narration_metrics.py.

Sources: artifacts/goal/narration/run*.json, product.narration.prompt/text.
Output: artifacts/goal/platform/eval/narration-holdout-v1.jsonl + summary.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.experiment_platform.narration_metrics import NAMES, clauses, parse_result  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / 'artifacts/goal/narration-decomp/narration-corpus.jsonl'
BUNDLE = ROOT / 'artifacts/goal/narration-standalone/inputs.jsonl'
RUN_GLOB = ROOT / 'artifacts/goal/narration/run*.json'
OUT = ROOT / 'artifacts/goal/platform/eval/narration-holdout-v1.jsonl'
SETTLE_MARK = '这一回合的结算结果：'
TIME_HEAD = '时间到了'


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text or '').strip()


def digest(text: str) -> str:
    return hashlib.sha256(normalize(text).encode('utf-8')).hexdigest()


def split_prompt(prompt: str) -> str | None:
    start = prompt.find('事实：')
    if start < 0:
        return None
    rest = prompt[start + 3:]
    end = rest.find('\n正文：')
    return rest[:end] if end >= 0 else rest


def split_settlement(rest: str) -> tuple[str, str]:
    index = rest.find(TIME_HEAD)
    if index < 0:
        return rest, ''
    cut = rest.rfind('。', 0, index)
    if cut < 0:
        return rest, ''
    return rest[:cut + 1].rstrip('（'), rest[cut + 1:]


def parse_facts_block(facts: str) -> tuple[str, str]:
    """Return (factsText, settlementText) exactly like build_bundle.py (E57)."""
    marker = facts.find(SETTLE_MARK)
    if marker < 0:
        return facts.strip(), ''
    head = facts[:marker]
    results, world = split_settlement(facts[marker + len(SETTLE_MARK):])
    return (head + world).strip(), results.strip()


def result_lines(settlement: str) -> list[str]:
    return [line.strip(' 。（') for line in re.split(r'[；;]', settlement) if line.strip(' 。（')]


def player_line(facts_text: str) -> str:
    return next((c.strip() for c in re.split(r'[。；]', facts_text) if '玩家这回合' in c), '')


def last_commits(paths: list[str]) -> dict[str, str]:
    proc = subprocess.run(
        ['git', '-C', str(ROOT), '-c', 'core.quotepath=false', 'log', '--format=@@%H', '--name-only', '--', 'artifacts/goal/narration'],
        capture_output=True, text=True, encoding='utf-8', errors='replace')
    mapping, commit = {}, None
    for line in (proc.stdout or '').splitlines():
        if line.startswith('@@'):
            commit = line[2:].strip()
        elif line.strip() and commit:
            mapping.setdefault(line.strip(), commit)
    return mapping


def load_hashes(path: Path, extract) -> set[str]:
    out = set()
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        value = extract(json.loads(line))
        if value:
            out.add(digest(value))
    return out


def build() -> tuple[list[dict], dict]:
    corpus_hashes = load_hashes(CORPUS, lambda r: split_prompt(r.get('prompt', '')))
    bundle_hashes = load_hashes(BUNDLE, lambda r: r.get('factsText'))
    commits = last_commits(sorted(glob.glob(str(RUN_GLOB))))
    files = sorted(glob.glob(str(RUN_GLOB)))
    rows, seen = [], set()
    stats = Counter()
    models, per_file = Counter(), Counter()
    for path in files:
        rel = Path(path).relative_to(ROOT).as_posix()
        try:
            doc = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError):
            stats['unreadable'] += 1
            continue
        for turn in doc.get('turns') or []:
            product = turn.get('product') or {}
            narration = product.get('narration') or {}
            prompt, text = narration.get('prompt'), narration.get('text')
            if not prompt or not text:
                continue
            stats['pairs'] += 1
            facts = split_prompt(prompt)
            if not facts:
                stats['noFacts'] += 1
                continue
            key = digest(facts)
            if key in corpus_hashes:
                stats['inCorpus'] += 1
                continue
            if key in bundle_hashes:
                stats['inBundle'] += 1
                continue
            if key in seen:
                stats['duplicate'] += 1
                continue
            facts_text, settlement = parse_facts_block(facts)
            lines = result_lines(settlement)
            model = product.get('narrationModel') or product.get('modelId') or 'unknown'
            outcomes = [r for r in (parse_result(x) for x in lines) if r and r['outcome']]
            expected_facts = [c for c in clauses(facts_text)
                              if len(c) > 4 and '做的事' not in c and '玩家这回合' not in c]
            if not expected_facts:
                stats['noExpectedFacts'] += 1
                continue
            names_in_input = facts_text + settlement + ' '.join(lines)
            point = narration.get('pointId') or turn.get('id') or '?'
            identity = f"nar-holdout:{Path(path).stem}:{turn.get('id')}:{point}"
            seen.add(key)
            models[model] += 1
            per_file[rel] += 1
            rows.append({
                'id': identity,
                'modality': 'narration',
                'world': 'dragon-raja-free-day',
                'split': 'test',
                'input': {'factsText': facts_text, 'settlementText': settlement,
                          'resultLines': lines, 'playerLine': player_line(facts_text),
                          'prompt': prompt},
                'expected': {'facts': expected_facts,
                             'outcomes': [{'actor': o['actor'], 'action': o['action'],
                                           'outcome': o['outcome']} for o in outcomes]},
                'forbidden': {'namesNotInInput': [n for n in NAMES if n not in names_in_input]},
                'provenance': {'labelSource': 'settlement-record', 'humanVerified': False,
                               'notes': 'fact block absent from narration corpus and the 161-point dev bundle'},
                'source': {'evidence': rel, 'turnId': turn.get('id'), 'pointId': point,
                           'model': model, 'commit': commits.get(rel)},
                'recorded': {'systemProse': text, 'model': model},
            })
    summary = {
        'schema': 'jity-narration-holdout/1',
        'stats': dict(stats),
        'selected': len(rows),
        'uniqueSources': len(per_file),
        'models': dict(models),
        'excluded': {'corpusFactHashes': len(corpus_hashes), 'bundleFactHashes': len(bundle_hashes)},
    }
    return sorted(rows, key=lambda r: r['id']), summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', default=str(OUT))
    parser.add_argument('--summary', default=None)
    args = parser.parse_args(argv)
    rows, summary = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8')
    canon = hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode('utf-8')).hexdigest()
    manifest = {'schema': 'jity-eval-set/1', 'path': out.relative_to(ROOT).as_posix(),
                'rows': len(rows), 'sha256': canon, 'hashMode': 'canonical-json'}
    (out.with_suffix('.jsonl.manifest.json')).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    summary_path = Path(args.summary) if args.summary else out.with_suffix('.summary.json')
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(out), 'rows': len(rows), **summary}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
