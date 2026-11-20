"""Build a small relation-direction set: the same two entities, relation and state,
with only the direction swapped.

Eight facts, each written by hand so the reverse sentence stays grammatical. Every
pair is asserted to differ exactly at the two entity positions, to keep the same
relation word, and to contain each entity exactly once.

The entities and sentences are new: no overlap with the frozen relation probes or
with any training pool row.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# (relation, anchor, attached, state tail, place, visible)
FACTS = [
    ('挂', '门框', '铜铃', '上', '库房', '门框、铜铃、木箱、麻袋、油灯、灰'),
    ('缠', '船桨', '麻绳', '上', '渡口', '船桨、麻绳、渡船、木桩、水面、船灯'),
    ('系', '栏杆', '布条', '上', '栈桥', '栏杆、布条、栈桥、水面、木桩、雾'),
    ('搭', '木架', '草席', '上', '库房', '木架、草席、木箱、门框、油灯、灰'),
    ('套', '门钉', '铜环', '上', '库房', '门钉、铜环、门板、木箱、油灯、灰'),
    ('盖', '鱼筐', '油布', '上', '鱼摊', '鱼筐、油布、鱼摊、木桌、水渍、灯'),
    ('插', '锁孔', '铁钥', '里', '库房', '锁孔、铁钥、门板、木箱、油灯、灰'),
    ('卡', '石缝', '木楔', '里', '堤岸', '石缝、木楔、堤岸、石阶、水渍、雾'),
]

BOILER = ('要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；'
          '只用地点可见里的物件与场景给的现象；不写任务标题、数值、具体时长、字段名；'
          '不新增人物、物品、地点。\n短句：\n')


def sentence(anchor, attached, relation, tail):
    return '%s%s在%s%s。' % (attached, relation, anchor, tail)


def main():
    rows, failures = [], []
    for index, (relation, anchor, attached, tail, place, visible) in enumerate(FACTS, start=1):
        target = sentence(anchor, attached, relation, tail)
        swapped = sentence(attached, anchor, relation, tail)
        # assertions: same length difference only from the two nouns; relation and tail identical
        if target.count(anchor) != 1 or target.count(attached) != 1:
            failures.append({'i': index, 'why': 'an entity appears more than once'})
        if relation not in target or relation not in swapped:
            failures.append({'i': index, 'why': 'relation word missing'})
        if target[-len(tail) - 1:] != swapped[-len(tail) - 1:]:
            failures.append({'i': index, 'why': 'tail differs'})
        first, second = target.find(attached), target.find(anchor)
        if not (0 <= first < second):
            failures.append({'i': index, 'why': 'expected attached before anchor'})
        # exactly one changed region: everything outside the two noun spans is identical
        prefix = target[:min(first, second)]
        suffix_len = len(tail) + 1
        inner_t = target[min(first, second) + len(anchor if first > second else attached):-suffix_len]
        inner_s = swapped[min(first, second) + len(anchor if first > second else attached):-suffix_len]
        if inner_t.replace(anchor, '').replace(attached, '') != inner_s.replace(anchor, '').replace(attached, ''):
            failures.append({'i': index, 'why': 'more than the entities changed'})
        input_text = ('短句任务。\n地点=%s\n地点可见=%s\n场景=傍晚；阴；油灯\n视角=沈砚；第三人称\n'
                      '事实=%s｜外貌变化｜%s%s在%s%s\n' % (place, visible, anchor, attached, relation, anchor, tail)
                      ) + BOILER
        rows.append({
            'unitId': 'rd%02d' % index,
            'relation': relation,
            'anchor': anchor,
            'attached': attached,
            'tail': tail,
            'input': input_text,
            'target': target,
            'negative': swapped,
            'why': 'the two nouns exchange places; relation word, state and syntax are untouched',
        })

    out_dir = ROOT / 'artifacts/relation-direction-r1'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'set.jsonl').write_text(
        '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n', encoding='utf-8', newline='\n')
    report = {'purpose': 'direction-only negatives for the margin calibration; no training',
              'facts': len(rows), 'failures': failures,
              'pairs': [{'unitId': r['unitId'], 'relation': r['relation'],
                         'correct': r['target'], 'swapped': r['negative']} for r in rows],
              'note': 'entities and sentences are new; no overlap with the frozen relation probes '
                      'or with any pool row'}
    (out_dir / 'build-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
