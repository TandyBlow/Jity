"""Which cf24 units are memorisable from the training pools?

A unit is treated as INDEPENDENT only when neither its rendered input nor its
fact signature (kind + subject + value, or kind + subject + from + to) appears
in the training pools. Units whose fact signature was trained on a different
context are labelled `seen-fact` and only count as regression checks: the model
has been taught that exact value, so a clean output there is not evidence that
it generalises.
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from component_paths import ComponentPaths  # noqa: E402

UNIT_FILE = 'world-components/n4-cf24-contract.jsonl'
# Local pool files are read from the worktree; the larger pools come from the
# pinned input root so their bytes are checked before use.
POOLS = (('verbalizer_pairs', HERE / 'n4_narrative_dev' / 'verbalizer_pairs.jsonl', None),
         ('expand-train80', None, 'world-components/n4-expand-train80.jsonl'),
         ('object-train40', None, 'world-components/n4-object-train40.jsonl'))


def fact_signature(fact, kind):
    if kind in ('moved', 'sanity_changed'):
        return (kind, fact.get('name'), fact.get('from'), fact.get('to'))
    return (kind, fact.get('name'), (fact.get('resultText') or fact.get('text') or '').strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--units', default=UNIT_FILE, help='Pinned unit file to check')
    parser.add_argument('--out', default='cf24-overlap.json')
    args = parser.parse_args()
    paths = ComponentPaths()
    run_dir = paths.output(args.run_dir)
    units = [json.loads(line) for line in paths.input(args.units).read_text(encoding='utf-8').splitlines() if line.strip()]

    signatures, inputs = {}, {}
    for label, local, pinned in POOLS:
        path = local if local is not None else paths.input(pinned)
        if not path.is_file():
            raise FileNotFoundError(f'Missing training pool: {path}')
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            signature = tuple(row.get('signature') or [])
            if signature:
                signatures.setdefault(signature, []).append(label)
            if row.get('input'):
                inputs.setdefault(row['input'], []).append(label)

    records, independent, seen = [], [], []
    for unit in units:
        signature = fact_signature(unit['fact'], unit['kind'])
        if unit['input'] in inputs:
            label, evidence = 'input-in-training', inputs[unit['input']]
        elif signature in signatures:
            label, evidence = 'seen-fact', signatures[signature]
        else:
            label, evidence = 'independent', []
        (independent if label == 'independent' else seen).append(unit['unitId'])
        records.append({'unitId': unit['unitId'], 'sourceId': unit['sourceId'],
                        'kind': unit['kind'], 'signature': list(signature),
                        'label': label, 'trainingPools': sorted(set(evidence))})

    report = {'unitFile': args.units,
              'pools': [label for label, _, _ in POOLS],
              'criterion': 'independent = neither the rendered input nor the fact signature occurs in a training pool',
              'counts': {'units': len(units), 'independent': len(independent), 'seen': len(seen)},
              'independentUnits': independent,
              'seenUnits': seen,
              'records': records}
    out = run_dir / args.out
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report['counts'], ensure_ascii=False))
    print('seen:', seen)
    print('->', out)


if __name__ == '__main__':
    main()
