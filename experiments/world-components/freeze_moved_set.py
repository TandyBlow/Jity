"""Freeze a movement-only validation set that nothing else already covers.

final24 has 7 movement units out of 76, so a movement regression is nearly
invisible there. This builds 24 single-fact movement units with

  * five subjects (沈砚, 叶知微, 阿棠, 韩渡, 顾行舟),
  * every world location as a start and as a destination,
  * uphill and downhill routes, and
  * endpoints whose names have aliases (渡口, 巷子, 灯塔, 档案馆, 集市, 堤面),

and refuses to write anything if a (subject, start, destination) signature
already appears in the training pools, cf24 or final24. The rendered input uses
the same scene and visible-prop lines that the existing contract files use for
each location, so only the fact differs.

The set is written as its own file and reported separately: final24 stays the
regression set it was frozen as, and the two are never merged into one
"independent" number.

Outputs:
  artifacts/next-inputs/world-components/n4-moved24-contract.jsonl
  artifacts/validation-freeze-r1/moved24-freeze.json
"""
import collections
import hashlib
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE = HERE.parents[1]
sys.path.insert(0, str(HERE))

from component_paths import ComponentPaths  # noqa: E402

PATHS = ComponentPaths(WORKTREE)
INPUTS = WORKTREE / 'artifacts/next-inputs/world-components'
FREEZE = WORKTREE / 'artifacts/validation-freeze-r1/moved24-freeze.json'
NAME = 'world-components/n4-moved24-contract.jsonl'
ELEVATION = {'潮生巷': 0, '早市': 0, '潮汐档案馆': 0, '潮渡': 0, '河心': 0, '雾堤': 1, '旧灯塔': 2}
LOCATION_LINE = {'潮生巷': '潮生巷', '早市': '早市', '潮汐档案馆': '潮汐档案馆', '潮渡': '潮渡>栈桥',
                 '雾堤': '雾堤>堤面', '旧灯塔': '旧灯塔>塔顶', '河心': '潮渡>栈桥'}
ALIASES = {'潮汐档案馆': ['档案馆'], '潮渡': ['渡口', '栈桥'], '旧灯塔': ['灯塔'], '雾堤': ['堤面', '堤上'],
           '潮生巷': ['巷子'], '早市': ['集市']}
# (subject, start, destination); none of these signatures exist in the pools,
# cf24 or final24.
ROUTES = [
    ('沈砚', '早市', '雾堤'), ('沈砚', '早市', '潮渡'), ('沈砚', '潮渡', '早市'),
    ('沈砚', '旧灯塔', '早市'), ('沈砚', '潮汐档案馆', '早市'), ('沈砚', '旧灯塔', '雾堤'),
    ('叶知微', '潮生巷', '潮汐档案馆'), ('叶知微', '潮汐档案馆', '旧灯塔'), ('叶知微', '潮渡', '雾堤'),
    ('叶知微', '旧灯塔', '潮汐档案馆'), ('叶知微', '早市', '潮渡'),
    ('阿棠', '早市', '潮渡'), ('阿棠', '潮渡', '旧灯塔'), ('阿棠', '潮汐档案馆', '早市'),
    ('阿棠', '潮生巷', '潮汐档案馆'), ('阿棠', '旧灯塔', '早市'),
    ('韩渡', '潮渡', '潮汐档案馆'), ('韩渡', '潮汐档案馆', '雾堤'), ('韩渡', '雾堤', '旧灯塔'),
    ('韩渡', '早市', '潮生巷'), ('韩渡', '雾堤', '潮渡'),
    ('顾行舟', '潮渡', '河心'), ('顾行舟', '潮渡', '早市'), ('顾行舟', '早市', '潮渡'),
]
REQUIREMENT = ('要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；'
               '只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；'
               '不写任务标题、数值、具体时长、字段名；不新增人物、物品、地点。')


def load(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def existing_signatures():
    signatures = set()
    sources = [WORKTREE / 'experiments/world-components/n4_narrative_dev/verbalizer_pairs.jsonl',
               INPUTS / 'n4-expand78-unified.jsonl', INPUTS / 'n4-object34-unified.jsonl',
               INPUTS / 'n4-cf24-contract.jsonl', INPUTS / 'n4-final24-contract.jsonl']
    for path in sources:
        for unit in load(path):
            if unit['kind'] != 'moved':
                continue
            if 'fact' in unit:
                fact = unit['fact']
                signatures.add((fact['name'], fact['from'], fact['to']))
            else:
                text = [line for line in unit['input'].splitlines() if line.startswith('事实=')][0][3:]
                parts = [piece.strip() for piece in text.split('｜')]
                start, end = parts[2].split('→')
                signatures.add((parts[0], start.strip(), end.strip()))
    return signatures


def context_lines():
    """Scene and visible-prop lines the contract files already use per location."""
    scenes, visible = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
    for path in sorted(INPUTS.glob('n4-*contract.jsonl')):
        for unit in load(path):
            fields = dict(line.split('=', 1) for line in unit['input'].splitlines() if '=' in line)
            if '地点' in fields and '场景' in fields:
                scenes[fields['地点']][fields['场景']] += 1
            if '地点' in fields and '地点可见' in fields:
                visible[fields['地点']][fields['地点可见']] += 1
    return ({key: value.most_common(1)[0][0] for key, value in scenes.items()},
            {key: value.most_common(1)[0][0] for key, value in visible.items()})


def direction(start, end):
    if ELEVATION[end] > ELEVATION[start]:
        return '上'
    if ELEVATION[end] < ELEVATION[start]:
        return '下'
    return '平'


def main():
    signatures = existing_signatures()
    scenes, visible = context_lines()
    units, hashes = [], {}
    for index, (subject, start, end) in enumerate(ROUTES, 1):
        assert (subject, start, end) not in signatures, ('signature already used', subject, start, end)
        assert start in ELEVATION and end in ELEVATION, (start, end)
        key = LOCATION_LINE[end]
        assert key in scenes and key in visible, key
        unit_id = 'm%02d:f0' % index
        text = '\n'.join(['短句任务。', '地点=' + key, '地点可见=' + visible[key], '场景=' + scenes[key],
                          '视角=%s；第三人称' % subject, '事实=%s｜移动｜%s→%s' % (subject, start, end),
                          '方向=' + direction(start, end), REQUIREMENT, '短句：', ''])
        should = '%s从%s到了%s。' % (subject, start, end)
        unit = {'unitId': unit_id, 'sourceId': 'm%02d' % index, 'kind': 'moved',
                'fact': {'factId': 'f0', 'kind': 'moved', 'name': subject, 'from': start, 'to': end,
                         'direction': direction(start, end)},
                'input': text, 'referenceTarget': should}
        units.append(unit)
        hashes[unit_id] = hashlib.sha256(text.encode('utf-8')).hexdigest()
    target = PATHS.inputs / NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(''.join(json.dumps(unit, ensure_ascii=False) + '\n' for unit in units),
                      encoding='utf-8', newline='\n')
    body = target.read_bytes()
    starts = collections.Counter(unit['fact']['from'] for unit in units)
    ends = collections.Counter(unit['fact']['to'] for unit in units)
    subjects = collections.Counter(unit['fact']['name'] for unit in units)
    freeze = {'set': 'moved24', 'frozenAt': '2026-11-05', 'units': len(units),
              'file': NAME, 'sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
              'inputSha256': hashes,
              'slices': {'moved24-new': [unit['unitId'] for unit in units]},
              'overlap': {'signatureOverlapWithPoolsOrExistingSets': 0,
                          'note': '河心 appears only as a destination here; existing training pairs '
                                  'already cover 河心 as a start for 顾行舟'},
              'coverage': {'subjects': dict(sorted(subjects.items())),
                           'starts': dict(sorted(starts.items())),
                           'destinations': dict(sorted(ends.items())),
                           'uphill': sum(1 for unit in units if unit['fact']['direction'] == '上'),
                           'downhill': sum(1 for unit in units if unit['fact']['direction'] == '下'),
                           'flat': sum(1 for unit in units if unit['fact']['direction'] == '平'),
                           'aliasedEndpoints': sorted(ALIASES)},
              'reporting': 'Reported as its own set. final24 keeps its role as the regression set; '
                           'the two are not merged into one independent number.'}
    FREEZE.parent.mkdir(parents=True, exist_ok=True)
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: freeze[k] for k in ('set', 'units', 'sha256', 'coverage', 'overlap')},
                     ensure_ascii=False, indent=1))
    print('->', target.relative_to(WORKTREE))


if __name__ == '__main__':
    main()
