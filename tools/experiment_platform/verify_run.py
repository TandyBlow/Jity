#!/usr/bin/env python3
"""Verify what a product run actually loaded and called.

Reads acceptance evidence JSON and checks, without trusting the report:
  - weight fetches: evidence.models.failed must be empty
  - engines: each required label exists and generated at least once
  - model ids: narrationModel/modelId contain the allowed id
  - semantic LLM calls: len(semanticPrompts) per turn under the cap
  - micro: every turn has microEnabled when required

  python -m tools.experiment_platform.verify_run --evidence results/product/evidence/x.json \
    --expect-model narration=qwen3-1.7b --max-llm-semantic 0 --require-micro
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


def check(doc: dict, allowed_models: dict[str, list[str]] | None = None,
          require_engines: list[str] | None = None, max_llm_semantic: int | None = None,
          require_micro: bool = False, forbid_program: bool = False) -> dict:
    failures = []
    models = doc.get('models') or {}
    if models.get('failed'):
        failures.append(f"weight fetch failed: {models.get('failed')}")
    engines = {}
    for turn in doc.get('turns') or []:
        for engine in (turn.get('product') or {}).get('engines') or []:
            label = engine.get('label') or '?'
            slot = engines.setdefault(label, {'loads': 0, 'generations': 0, 'contextSize': set()})
            slot['loads'] += int(engine.get('loadCount') or 0)
            slot['generations'] += int(engine.get('generations') or 0)
            if engine.get('contextSize'):
                slot['contextSize'].add(engine['contextSize'])
    for label in require_engines or []:
        if label not in engines or engines[label]['generations'] <= 0:
            failures.append(f'engine {label} missing or never generated')
    llm_semantic = 0
    program_turns = 0
    for index, turn in enumerate(doc.get('turns') or []):
        product = turn.get('product') or {}
        llm_semantic += len(product.get('semanticPrompts') or [])
        if product.get('source') == 'program' or product.get('narrationModel') == 'rules':
            program_turns += 1
        if allowed_models:
            for role in ('narration',):
                allowed = allowed_models.get(role)
                value = product.get('narrationModel') or product.get('modelId') or ''
                if allowed and not any(a in str(value) for a in allowed):
                    failures.append(f'turn {index} {role} model {value!r} not in {allowed}')
        if require_micro and not product.get('microEnabled'):
            failures.append(f'turn {index} micro disabled')
    if max_llm_semantic is not None and llm_semantic > max_llm_semantic:
        failures.append(f'LLM semantic prompts {llm_semantic} > cap {max_llm_semantic}')
    if forbid_program and (doc.get('programNarrationAccepted') or program_turns):
        failures.append(f'program narration accepted or present in {program_turns} turns')
    return {
        'runId': doc.get('runId'), 'status': doc.get('status'), 'turns': len(doc.get('turns') or []),
        'models': {'requests': models.get('requests'), 'ok': models.get('ok'), 'failed': models.get('failed')},
        'engines': {k: {'loads': v['loads'], 'generations': v['generations'],
                        'contextSize': sorted(v['contextSize'])} for k, v in engines.items()},
        'llmSemanticPrompts': llm_semantic,
        'programNarrationAccepted': bool(doc.get('programNarrationAccepted')),
        'programTurns': program_turns,
        'failures': failures, 'pass': not failures,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--evidence', required=True, help='file or glob')
    parser.add_argument('--expect-model', action='append', default=[],
                        help='role=id|id2 (currently narration)')
    parser.add_argument('--require-engine', default='')
    parser.add_argument('--max-llm-semantic', type=int, default=None)
    parser.add_argument('--require-micro', action='store_true')
    parser.add_argument('--forbid-program', action='store_true',
                        help='fail if the run accepted program narration (rules arm)')
    parser.add_argument('--out', default=None)
    args = parser.parse_args(argv)
    allowed: dict[str, list[str]] = {}
    for spec in args.expect_model:
        role, _, ids = spec.partition('=')
        allowed[role] = [x.strip() for x in ids.split('|') if x.strip()]
    engines = [x.strip() for x in args.require_engine.split(',') if x.strip()]
    paths = sorted(glob.glob(args.evidence))
    if not paths:
        print('no evidence files', file=sys.stderr)
        return 2
    reports = []
    for path in paths:
        try:
            doc = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        except (OSError, json.JSONDecodeError) as exc:
            reports.append({'file': str(path).replace('\\', '/'), 'pass': False,
                            'failures': [f'unreadable: {exc}']})
            continue
        report = check(doc, allowed, engines, args.max_llm_semantic, args.require_micro,
                       args.forbid_program)
        report['file'] = str(path).replace('\\', '/')
        reports.append(report)
    payload = {'schema': 'jity-run-verify/1', 'reports': reports,
               'failed': sum(1 for r in reports if not r['pass'])}
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(text)
    return 1 if payload['failed'] else 0


if __name__ == '__main__':
    sys.exit(main())
