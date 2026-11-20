"""Deterministic edit layer over an existing cf24 run (no regeneration).

Rule `moved-drop-unrelated-tail`: for a moved unit, keep the first clause and
any later clause that carries the start or the destination; drop the rest.

The guard matters: a clause is never dropped when it is the only place the
start or the destination appears, so the edit cannot turn a supported move into
a missing one. Edits are recorded per unit with the original and resulting text.
"""
import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from component_paths import ComponentPaths  # noqa: E402

ALIASES = {'潮汐档案馆': ['档案馆'], '潮渡': ['渡口', '栈桥'], '旧灯塔': ['灯塔'], '雾堤': ['堤面', '堤上'],
           '潮生巷': ['巷子'], '早市': ['集市']}
RULES = ('moved-drop-unrelated-tail',)


def carries(text, place):
    if not place:
        return False
    return place in text or any(alias in text for alias in ALIASES.get(place, []))


def edit_moved(text, fact):
    start, destination = fact.get('from'), fact.get('to')
    body = text.rstrip()
    ending = ''
    if body.endswith('。'):
        body, ending = body[:-1], '。'
    clauses = [part for part in re.split(r'(?<=[，,])', body)]
    if len(clauses) < 2:
        return text, None
    kept = [clauses[0]]
    dropped = []
    for clause in clauses[1:]:
        if carries(clause, start) or carries(clause, destination):
            kept.append(clause)
        else:
            dropped.append(clause)
    if not dropped:
        return text, None
    remaining = ''.join(kept).rstrip('，,、 ')
    if not (carries(remaining, start) and carries(remaining, destination)):
        return text, None
    return remaining + ending, {'droppedClauses': dropped, 'result': remaining + ending}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--source', default='cf24-baseline.json')
    parser.add_argument('--rule', choices=RULES, default=RULES[0])
    args = parser.parse_args()
    paths = ComponentPaths()
    run_dir = paths.output(args.run_dir)
    report = json.loads((run_dir / args.source).read_text(encoding='utf-8'))

    edits, rows = [], []
    for row in report['rows']:
        text = row['text']
        if row['kind'] == 'moved':
            text, record = edit_moved(text, row['fact'])
            if record:
                edits.append({'unitId': row['unitId'], 'sourceId': row['sourceId'],
                              'before': row['text'], **record})
        updated = dict(row, text=text, editedBy=args.rule if text != row['text'] else None)
        rows.append(updated)

    out = dict(report, rows=rows,
               editLayer={'rule': args.rule, 'editedUnits': len(edits), 'edits': edits})
    out.pop('editedBy', None)
    target = run_dir / 'cf24-edited.json'
    target.write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({'rule': args.rule, 'editedUnits': len(edits),
                      'units': [e['unitId'] for e in edits]}, ensure_ascii=False, indent=1))
    print('->', target)


if __name__ == '__main__':
    main()
