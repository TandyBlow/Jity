"""Build the direction-margin training set and the round's holdout.

Training: twelve facts, each with a correct sentence and a legal reversal that keeps the two
entities, the relation and the state. Holdout: eight facts with different entities and different
relations, used only for free generation.

The reversal is the same shape that the six confirmed rows fail on: the name taken as the agent
of the relation. Everything else in the sentence is held fixed.
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# relation, anchor, attached, state, place, visible
TRAIN = [
    ('压', '石磨', '竹篓', '歪了', '磨坊', '石磨、竹篓、木梁、麻袋、油灯、灰'),
    ('靠', '木箱', '铁铲', '滑下来', '库房', '木箱、铁铲、门框、麻袋、油灯、灰'),
    ('堆', '竹筐', '干柴', '露出来', '柴房', '竹筐、干柴、木架、麻绳、油灯、灰'),
    ('插', '灯台', '蜡烛', '倒了', '书房', '灯台、蜡烛、书案、铜镇、窗纸、灯'),
    ('搭', '绳梯', '麻绳', '垂下来', '塔顶', '绳梯、麻绳、铜灯罩、铁链、海风、雾'),
    ('缠', '木桶', '草绳', '散了', '后院', '木桶、草绳、石阶、水缸、井绳、灯'),
    ('挂', '木钉', '铜盆', '晃了', '灶间', '木钉、铜盆、灶台、陶碗、水汽、灯'),
    ('系', '竹竿', '布条', '松了', '晒场', '竹竿、布条、竹篮、草席、日头、风'),
    ('套', '陶罐', '铜环', '歪了', '库房', '陶罐、铜环、木箱、麻袋、油灯、灰'),
    ('卡', '石阶', '铁钉', '露出来', '堤岸', '石阶、铁钉、堤岸、水渍、木桩、雾'),
    ('盖', '鱼篓', '油布', '滑开了', '鱼摊', '鱼篓、油布、案板、水渍、灯、白汽'),
    ('靠', '石碾', '竹竿', '倒了', '磨坊', '石碾、竹竿、石磨、麻袋、油灯、灰'),
]
HOLDOUT = [
    ('压', '石缸', '木板', '裂了', '井边', '石缸、木板、井绳、水渍、石阶、雾'),
    ('靠', '木梯', '竹篙', '滑下来', '渡口', '木梯、竹篙、渡船、缆绳、船灯、水面'),
    ('堆', '竹篮', '干草', '露出来', '柴房', '竹篮、干草、木架、麻绳、油灯、灰'),
    ('插', '铜壶', '铁签', '歪了', '书房', '铜壶、铁签、书案、窗纸、灯、灰'),
    ('搭', '木凳', '草垫', '滑下来', '后院', '木凳、草垫、石阶、水缸、井绳、灯'),
    ('缠', '铁锚', '麻线', '断了', '堤岸', '铁锚、麻线、堤岸、缆绳、水面、雾'),
    ('挂', '铁钩', '陶碗', '晃了', '灶间', '铁钩、陶碗、灶台、铜盆、水汽、灯'),
    ('系', '车辕', '布带', '松了', '晒场', '车辕、布带、竹竿、草席、日头、风'),
]

BOILER = ('要求：写一句话，把事实写成场景里可见的动作或状态；句中出现事实主体的名字；'
          '只用地点可见里的物件与场景给的现象；需要表示高低时用方向给的字；不写任务标题、数值、'
          '具体时长、字段名；不新增人物、物品、地点。\n短句：\n')


def pair(relation, anchor, attached, state):
    correct = '%s在%s上的%s%s。' % (relation, anchor, attached, state)
    if relation in ('堆', '插'):
        correct = '%s在%s里的%s%s。' % (relation, anchor, attached, state)
    reversed_ = '%s%s着的%s%s。' % (anchor, relation, attached, state)
    return correct, reversed_


def build(entries, prefix, kind):
    rows, failures = [], []
    for index, (relation, anchor, attached, state, place, visible) in enumerate(entries, start=1):
        correct, reversed_ = pair(relation, anchor, attached, state)
        for text, label in ((correct, 'correct'), (reversed_, 'reversed')):
            for token in (anchor, attached, relation, state):
                if token not in text:
                    failures.append({'row': '%s%02d' % (prefix, index), 'why': '%s missing %s' % (label, token)})
        if correct.count(anchor) != 1 or correct.count(attached) != 1:
            failures.append({'row': '%s%02d' % (prefix, index), 'why': 'an entity appears more than once'})
        input_text = ('短句任务。\n地点=%s\n地点可见=%s\n场景=傍晚；阴；油灯\n视角=沈砚；第三人称\n'
                      '事实=%s｜外貌变化｜%s\n' % (place, visible, anchor, correct.rstrip('。'))) + BOILER
        rows.append({
            'unitId': '%s%02d' % (prefix, index),
            'kind': kind,
            'relation': relation,
            'anchor': anchor,
            'attached': attached,
            'state': state,
            'input': input_text,
            'target': correct,
            'negative': reversed_,
        })
    return rows, failures


def main():
    train, f1 = build(TRAIN, 'mt', 'appearance_changed')
    holdout, f2 = build(HOLDOUT, 'mo', 'appearance_changed')
    train_entities = {e for _, a, b, _, _, _ in TRAIN for e in (a, b)}
    hold_entities = {e for _, a, b, _, _, _ in HOLDOUT for e in (a, b)}
    overlap = train_entities & hold_entities
    assert not overlap, overlap

    out_dir = ROOT / 'artifacts/margin-r1'
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'train.jsonl').write_text(
        '\n'.join(json.dumps(r, ensure_ascii=False) for r in train) + '\n', encoding='utf-8', newline='\n')
    (out_dir / 'holdout.jsonl').write_text(
        '\n'.join(json.dumps(r, ensure_ascii=False) for r in holdout) + '\n', encoding='utf-8', newline='\n')
    (out_dir / 'train-negatives.jsonl').write_text(
        '\n'.join(json.dumps({'unitId': r['unitId'], 'negative': r['negative']}, ensure_ascii=False)
                  for r in train) + '\n', encoding='utf-8', newline='\n')

    holdout_units = [{'unitId': r['unitId'], 'input': r['input'], 'kind': 'appearance_changed',
                      'fact': {'kind': 'appearance_changed', 'name': r['anchor'],
                               'text': r['target'].rstrip('。')}}
                     for r in holdout]
    (out_dir / 'holdout-units.jsonl').write_text(
        '\n'.join(json.dumps(u, ensure_ascii=False) for u in holdout_units) + '\n', encoding='utf-8', newline='\n')

    report = {'purpose': 'direction-margin arms: twelve training facts, eight holdout facts',
              'train': len(train), 'holdout': len(holdout),
              'failures': f1 + f2,
              'entityOverlap': sorted(overlap),
              'relations': {'train': sorted({r['relation'] for r in train}),
                            'holdout': sorted({r['relation'] for r in holdout})},
              'pairs': [{'unitId': r['unitId'], 'correct': r['target'], 'reversed': r['negative']} for r in train],
              'holdoutPairs': [{'unitId': r['unitId'], 'correct': r['target'], 'reversed': r['negative']}
                               for r in holdout]}
    (out_dir / 'build-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: report[k] for k in ('train', 'holdout', 'failures', 'relations')}, ensure_ascii=False))
    for r in train + holdout:
        print('%-5s %s | %s || %s' % (r['unitId'], r['relation'], r['target'], r['negative']))


if __name__ == '__main__':
    main()
