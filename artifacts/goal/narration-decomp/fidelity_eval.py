# -*- coding: utf-8 -*-
"""Fidelity of the generated prose against its plan: plan coverage (share of
plan content words present) and inventions (content words absent from the
plan). Char overlap rewards copying; these numbers say whether the text is
grounded in the planned facts."""
import json
import re
from pathlib import Path

import jieba

HERE = Path(__file__).resolve().parent
STOP = set('的 了 着 过 地 得 是 在 把 被 将 让 给 向 从 对 与 和 及 而 却 便 就 都 也 还 很 更 最 又 再 才 只 分 他 她 它 他们 她们 它们 自己 对方 这 那 其 我 你 我们 你们 一个 一 二 三 两 之 于 为 以 所 但 然 后 里 上 下 中 前 后 边 面 头'.split())
PUNCT = re.compile(r'^[，。！？；：、"' + "'" + r'（）\n…—\s]+$')


def strip_prefix(clause: str) -> str:
    body = re.sub(r'^玩家这回合.*?做的事：', '', clause)
    body = re.sub(r'^这一回合的结算结果：', '', body)
    body = re.sub(r'^[一-龥]{1,4}[：:]', '', body)
    return body.strip()


def words(text: str):
    return [w for w in jieba.lcut(text) if not PUNCT.match(w) and w not in STOP and len(w) >= 1]


def main():
    plans = [json.loads(l) for l in (HERE / 'planning-examples-v2.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    by_prefix = {}
    for plan in plans:
        text = '|'.join(f"{plan['types'][i]}{strip_prefix(plan['clauses'][i])}" for i in plan['selected'])
        by_prefix[text[:120]] = plan
    audits = [json.loads(l) for l in (HERE / 'plan-to-prose-samples.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    coverage, inventions = [], []
    matched = 0
    for row in audits:
        plan = by_prefix.get(row['plan'][:120])
        if not plan:
            continue
        matched += 1
        plan_words = set()
        for index in plan['selected']:
            plan_words.update(words(plan['clauses'][index]))
        gen_words = words(row['generated'])
        if not gen_words:
            coverage.append(0.0); inventions.append(0)
            continue
        present = sum(1 for w in plan_words if w in row['generated'])
        coverage.append(present / max(1, len(plan_words)))
        inventions.append(sum(1 for w in gen_words if w not in plan_words))
    mean_cov = sum(coverage) / max(1, len(coverage))
    mean_inv = sum(inventions) / max(1, len(inventions))
    print(json.dumps({'matched': matched, 'samples': len(audits),
                      'planCoverageMean': round(mean_cov, 3),
                      'inventionWordsMean': round(mean_inv, 1)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
