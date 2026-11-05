"""等价性验证：原版整段重算 vs KV 缓存版，逐 token 与最终分数对比。

覆盖：双项事实、重复案例、移动、父路径切换、不同路径先后结束。
不生成新文本，不改搜索规则。
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fact_contract as FC  # noqa: E402
from beam_decode import generate_beam_cached, generate_beam_recompute  # noqa: E402

import sys as _paths_sys
_paths_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from component_paths import PATHS

ART = PATHS.input('decode-compare')


def load_cases():
    cases = []
    for name, tag in (('cases.json', 'small'), ('confirm40.json', 'confirm'),
                      ('diag215-cases.json', 'diag')):
        payload = json.loads((ART / name).read_text(encoding='utf-8'))
        for case in payload['cases']:
            cases.append({'tag': tag, **case})
    return cases


def pick(cases):
    """按覆盖目标挑选：双项、重复、移动，并有意包含已知会切换父路径的案例。"""
    chosen, seen = [], set()

    def take(predicate, limit):
        for case in cases:
            if len([c for c in chosen if predicate(c)]) >= limit:
                break
            if case['caseId'] in seen:
                continue
            if predicate(case):
                chosen.append(case)
                seen.add(case['caseId'])

    take(lambda c: '也' in (c.get('factText') or ''), 6)          # 双项
    take(lambda c: c['caseId'] in ('train-r1:f1', 'fixture-r1:f1',
                                   'train-r4:f1', 'ca4B', 'd038'), 5)   # 重复
    take(lambda c: c['kind'] == 'moved', 10)                       # 移动
    take(lambda c: c['caseId'] in ('t11:f1', 't23:f2', 'v01:f0'), 3)
    take(lambda c: True, 6)                                        # 其余补充
    return chosen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', '--ckpt', dest='ckpt', default=None)
    parser.add_argument('--budget', type=float, default=20.0)
    parser.add_argument('--out', default=str(PATHS.output('decode-compare/beam-cache-equivalence.json')))
    args = parser.parse_args()
    args.ckpt = str(PATHS.model(args.ckpt))
    args.out = str(PATHS.output(args.out))
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    cases = pick(load_cases())
    FC.check_units([{'unitId': c['caseId'], 'kind': c['kind'], 'input': c['input']}
                    for c in cases])

    tokenizer = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.ckpt, torch_dtype=torch.float32)
    model.to('cpu').eval()

    rows = []
    for case in cases:
        encoded = tokenizer(case['input'], return_tensors='pt',
                            truncation=False).to('cpu')
        tokens_a, meta_a = generate_beam_recompute(model, encoded, 2, args.budget)
        tokens_b, meta_b = generate_beam_cached(model, encoded, 2, args.budget)
        same_tokens = tokens_a == tokens_b
        score_gap = abs(meta_a['score'] - meta_b['score'])
        rows.append({'caseId': case['caseId'], 'tag': case['tag'],
                     'kind': case['kind'], 'fact': case.get('factText'),
                     'tokensEqual': same_tokens,
                     'textA': tokenizer.decode(tokens_a, skip_special_tokens=True),
                     'textB': tokenizer.decode(tokens_b, skip_special_tokens=True),
                     'scoreA': meta_a['score'], 'scoreB': meta_b['score'],
                     'scoreGap': round(score_gap, 9),
                     'switches': meta_b['switches'],
                     'secondsA': meta_a['seconds'], 'secondsB': meta_b['seconds'],
                     'completeA': meta_a['complete'], 'completeB': meta_b['complete']})
        print(json.dumps({'case': case['caseId'], 'equal': same_tokens,
                          'gap': rows[-1]['scoreGap'], 'switches': meta_b['switches'],
                          'A': rows[-1]['textA'], 'B': rows[-1]['textB']},
                         ensure_ascii=False), flush=True)

    summary = {'cases': len(rows),
               'tokensEqual': sum(1 for r in rows if r['tokensEqual']),
               'maxScoreGap': max((r['scoreGap'] for r in rows), default=0),
               'casesWithSwitch': sum(1 for r in rows if r['switches'] > 0),
               'secondsA': round(sum(r['secondsA'] for r in rows), 2),
               'secondsB': round(sum(r['secondsB'] for r in rows), 2),
               'complete': sum(1 for r in rows if r['completeB'])}
    pathlib.Path(args.out).write_text(json.dumps({'summary': summary, 'rows': rows},
                                                 ensure_ascii=False, indent=1),
                                      encoding='utf-8')
    print('SUMMARY', json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
