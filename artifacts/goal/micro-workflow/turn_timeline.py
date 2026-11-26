# -*- coding: utf-8 -*-
"""Per-turn execution timeline from product acceptance evidence.

Reads the semantic-call ledger, point narration, micro stats and engine
counters already recorded by the page; adds no instrumentation to the app.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def ms(value):
    return round(value or 0)


def main():
    for name in sys.argv[1:]:
        data = json.loads(Path(name).read_text(encoding='utf8'))
        print(f'# {Path(name).name} status={data.get("status")}')
        for turn in data.get('turns') or []:
            product = turn.get('product') or {}
            calls = [call for call in product.get('semanticCalls') or []]
            timed = [call for call in calls if call.get('ms') is not None]
            by_task = defaultdict(lambda: {'calls': 0, 'ms': 0, 'fallback': 0, 'attempts': 0, 'errors': 0})
            by_stage = defaultdict(lambda: {'calls': 0, 'ms': 0})
            for call in timed:
                task = call.get('task') or '?'
                row = by_task[task]
                row['calls'] += 1
                row['ms'] += call.get('ms') or 0
                row['fallback'] += 1 if call.get('fallback') else 0
                row['attempts'] += 1 if call.get('attempt') else 0
                row['errors'] += 1 if call.get('error') else 0
                for stage in call.get('stages') or []:
                    stage_row = by_stage[stage]
                    stage_row['calls'] += 1
                    stage_row['ms'] += call.get('ms') or 0
            micro = defaultdict(lambda: {'calls': 0, 'ms': 0})
            for row in product.get('microStats') or []:
                port = row.get('port') or '?'
                micro[port]['calls'] += 1
                micro[port]['ms'] += row.get('ms') or 0
            duplicate = Counter(
                (call.get('task'), call.get('key'), tuple(call.get('stages') or []))
                for call in timed if not call.get('attempt')
            )
            repeated = [(key, count) for key, count in duplicate.items() if count > 1]
            timings = turn.get('timings') or {}
            print(f'\n## turn {turn.get("turn")} {turn.get("input", "")!r} problems={turn.get("problems")}')
            print(f'wait={ms(timings.get("doneMs"))}ms firstVisible={ms(timings.get("firstVisibleDraftMs"))}ms '
                  f'accepted={ms(product.get("acceptedMs"))}ms chars={turn.get("shownChars")}')
            print('| task | calls | ms | fallback | attempts | errors |')
            print('|---|---:|---:|---:|---:|---:|')
            for task, row in sorted(by_task.items(), key=lambda item: -item[1]['ms']):
                print(f'| {task} | {row["calls"]} | {ms(row["ms"])} | {row["fallback"]} | {row["attempts"]} | {row["errors"]} |')
            if by_stage:
                print('| updates stage | calls | ms |')
                print('|---|---:|---:|')
                for stage, row in sorted(by_stage.items(), key=lambda item: -item[1]['ms']):
                    print(f'| {stage} | {row["calls"]} | {ms(row["ms"])} |')
            if micro:
                print('micro: ' + ', '.join(f'{port} {row["calls"]}/{ms(row["ms"])}ms' for port, row in sorted(micro.items())))
            action_calls = [call for call in calls if call.get('task') == 'action']
            if action_calls:
                sources = Counter(call.get('source') or '?' for call in action_calls)
                attempts = sum(1 for call in action_calls if call.get('attempt'))
                print(f'action sources {dict(sources)} attempts={attempts} '
                      f'llm_calls={sum(1 for call in action_calls if (call.get("ms") or 0) > 0)}')
            if repeated:
                print('repeated accepted calls: ' + ', '.join(f'{key} x{count}' for key, count in repeated[:10]))
            engines = product.get('engines') or []
            if engines:
                print('engines: ' + ', '.join(
                    f'{engine.get("label")} loads={engine.get("loadCount")} lastLoad={ms(engine.get("lastLoadMs"))}ms ctx={engine.get("contextSize")}'
                    for engine in engines
                ))


if __name__ == '__main__':
    main()
