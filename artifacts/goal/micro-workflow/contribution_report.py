# -*- coding: utf-8 -*-
"""Contribution accounting for the hybrid micro arm, from acceptance evidence.

Counts, per the five-arm protocol: micro inference calls by port, program
calls, LLM generations by engine, validation retries, abstain/fallback rows,
and the per-stage / whole-turn time. No interpretation, only what the
evidence recorded."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / 'evidence-perf-taskskip-8.json'
    data = json.loads(path.read_text(encoding='utf8'))
    turns = data.get('turns') or []
    micro_by_port = Counter()
    micro_inferences = Counter()
    micro_ms = Counter()
    program_calls = 0
    llm_by_engine = Counter()
    llm_ms = Counter()
    llm_prompt_tokens = 0
    llm_cached_tokens = 0
    llm_retries = 0
    abstain_rows = 0
    fallback_rows = 0
    stage_ms = Counter()
    waits = []
    seen_generations = set()
    for turn in turns:
        waits.append(((turn.get('timings') or {}).get('waitMs') or 0) / 1000)
        for row in (turn.get('product') or {}).get('microStatsAll') or []:
            port = row.get('port') or '?'
            source = row.get('source') or 'micro'
            if source == 'micro':
                micro_by_port[port] += 1
                count = row['inferences'] if 'inferences' in row else (row.get('pairs') if 'pairs' in row else (row.get('calls') or 0))
                micro_inferences[port] += int(count or 0)
                micro_ms[port] += float(row['ms'] if 'ms' in row else ((row.get('inferMs') or 0) + (row.get('buildMs') or 0)))
            elif source == 'abstain':
                abstain_rows += 1
            else:
                program_calls += 1
        for call in (turn.get('submission') or {}).get('calls') or []:
            stage = call.get('stage') or call.get('task') or '?'
            stage_ms[stage] += call.get('ms') or 0
            if call.get('fallback'):
                fallback_rows += 1
            attempts = call.get('attempts')
            if isinstance(attempts, int) and attempts > 1:
                llm_retries += attempts - 1
        for gen in turn.get('generations') or []:
            marker = gen.get('at')
            if marker in seen_generations:
                continue
            seen_generations.add(marker)
            engine = gen.get('engine') or '?'
            llm_by_engine[engine] += 1
            llm_ms[engine] += gen.get('wallMs') or 0
            llm_prompt_tokens += gen.get('promptTokens') or 0
            llm_cached_tokens += gen.get('cachedPromptTokens') or 0
    report = {
        'evidence': path.name, 'turns': len(turns),
        'meanTurnS': round(sum(waits) / max(1, len(waits)), 1),
        'micro': {'rowsByPort': dict(micro_by_port), 'inferencesByPort': dict(micro_inferences),
                  'msByPort': {k: round(v) for k, v in micro_ms.items()},
                  'totalRows': sum(micro_by_port.values()), 'totalInferences': sum(micro_inferences.values())},
        'program': {'rows': program_calls, 'abstainRows': abstain_rows},
        'llm': {'generationsByEngine': dict(llm_by_engine), 'msByEngine': {k: round(v) for k, v in llm_ms.items()},
                'promptTokens': llm_prompt_tokens, 'cachedPromptTokens': llm_cached_tokens,
                'retries': llm_retries, 'fallbackRows': fallback_rows},
        'stageMs': {k: round(v) for k, v in sorted(stage_ms.items(), key=lambda kv: -kv[1])},
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
