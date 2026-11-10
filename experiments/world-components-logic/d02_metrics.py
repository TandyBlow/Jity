"""Summarize the proxy API checker run without treating it as model evidence."""
from __future__ import annotations
import json
from pathlib import Path
import statistics
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import short_d02_checkers as checkers
from d02_api_experiment import assemble_audits, parse_json

DATA = HERE / 'data' / 'd02-checkers' / 'pilot-v1'
ART = HERE.parents[1] / 'artifacts' / 'world-components-logic' / 'd02-checkers'


def load_samples(source):
    rows = [json.loads(line) for line in (DATA / 'samples.jsonl').read_text().splitlines()]
    return {row['sampleId']: row for row in rows if row['source'] == source}


def summarize(run_path, source):
    samples = load_samples(source)
    worlds = json.loads((DATA / 'worlds.json').read_text())
    rows = [json.loads(line) for line in run_path.read_text().splitlines() if line.strip()]
    metrics = {'run': run_path.name, 'source': source, 'requests': len(rows),
               'status': {}, 'decisions': {}, 'parsed': 0, 'exact': 0,
               'expectedAccept': 0, 'expectedUpgrade': 0,
               'trueAccept': 0, 'trueUpgrade': 0, 'falseAccepts': [], 'falseUpgrades': [],
               'incomplete': 0, 'malformed': [], 'programCodes': {}, 'latencies': [],
               'usage': {'prompt': 0, 'completion': 0, 'total': 0}, 'estimatedCny': 0}
    for row in rows:
        sample = samples.get(row['sampleId'])
        if sample is None:
            continue
        expected = sample['expected']['combined']
        metrics['expectedAccept' if expected == 'accept' else 'expectedUpgrade'] += 1
        metrics['status'][row.get('status')] = metrics['status'].get(row.get('status'), 0) + 1
        metrics['estimatedCny'] += row.get('estimatedCny', 0)
        for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
            metrics['usage'][{'prompt_tokens': 'prompt', 'completion_tokens': 'completion',
                              'total_tokens': 'total'}[key]] += row.get('usage', {}).get(key, 0)
        metrics['latencies'].append(row.get('latencyMs', 0))
        decision = row.get('decision')
        if row.get('parsed'):
            metrics['parsed'] += 1
        if decision is None:
            metrics['malformed'].append({'sampleId': row['sampleId'], 'error': row.get('error')})
            continue
        metrics['decisions'][decision] = metrics['decisions'].get(decision, 0) + 1
        if decision == expected:
            metrics['exact'] += 1
        if decision == 'accept' and expected == 'accept':
            metrics['trueAccept'] += 1
        elif decision == 'accept' and expected != 'accept':
            metrics['falseAccepts'].append(row['sampleId'])
        elif decision == 'upgrade' and expected == 'upgrade':
            metrics['trueUpgrade'] += 1
        elif decision == 'upgrade' and expected == 'accept':
            metrics['falseUpgrades'].append(row['sampleId'])
        elif decision == 'incomplete':
            metrics['incomplete'] += 1
        try:
            parsed = parse_json(row['raw'])
            role, expr = assemble_audits(parsed, sample['text'])
            result = checkers.check_once(sample['text'], sample['steps'], role, expr,
                                         worlds[sample['worldId']], sample['actorId'])
            for issue in result.issues:
                metrics['programCodes'][issue['code']] = metrics['programCodes'].get(issue['code'], 0) + 1
        except Exception as exc:
            metrics['programCodes']['parse_or_contract_error'] = \
                metrics['programCodes'].get('parse_or_contract_error', 0) + 1
    lat = sorted(metrics.pop('latencies'))
    if lat:
        metrics['latencyP50Ms'] = lat[len(lat) // 2]
        metrics['latencyP95Ms'] = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
    metrics['programCodes'] = dict(sorted(metrics['programCodes'].items(),
                                          key=lambda item: -item[1]))
    return metrics


def main():
    ART.mkdir(parents=True, exist_ok=True)
    targets = []
    for tag, source in (('targeted-r1', 'assistant_authored_targeted'),
                        ('natural-r1', 'api_first_output')):
        path = DATA / 'api' / ('checker-%s.jsonl' % tag)
        if path.exists():
            targets.append(summarize(path, source))
    summary = {
        'schema': 'jity-d02-proxy-api-checker-summary-v1',
        'model': 'deepseek-flash (proxy, non-thinking, one-shot checker)',
        'notEvidenceFor': ['trained M1/M2', 'production API version', 'A/B/C comparison'],
        'runs': targets,
    }
    (ART / 'proxy-checker-summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
