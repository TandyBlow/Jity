# -*- coding: utf-8 -*-
"""E60: cumulative (per evidence run) and per-point comparison of the four
narration arms. Cumulative is the player-facing view: a fact only has to be
said once across the run."""
import json
from collections import defaultdict
from pathlib import Path

import cluster_events as ce
import evaluate_narration as ev
from role_parse import parse_result

HERE = Path(__file__).resolve().parent


def load(name):
    return {r['id']: r for r in json.load(open(HERE / name, encoding='utf8'))}


def arms_for(rows, delta, cand):
    by = defaultdict(list)
    for r in rows:
        by[r['evidence']].append(r)
    for evid, rs in by.items():
        yield evid, rs


def main():
    rows = [json.loads(l) for l in (HERE / 'inputs.jsonl').read_text(encoding='utf8').splitlines() if l.strip()]
    delta = load('compose-delta-rows.json')
    cand = load('compose-candidate-rows.json')

    def text_of(arm, r):
        if arm == 'current-1.7b':
            return r['systemProse'] or ''
        if arm == 'rules-e57':
            return ce.compose(r)[0]
        if arm == 'delta-e59':
            return delta[r['id']]['text']
        return cand[r['id']]['text']

    by = defaultdict(list)
    turn_stats = {}
    for r in rows:
        by[r['evidence']].append(r)
        k = (r['evidence'], r['turnId'])
        ts = turn_stats.setdefault(k, {'chars': len(r['systemProse'] or ''),
                                       'sent': len(ev.sentences(r['systemProse'] or '')), 'n': 0})
        ts['n'] += 1

    report = {}
    for arm in ('current-1.7b', 'rules-e57', 'delta-e59', 'candidate-e60'):
        tot_f = hit_f = tot_o = hit_o = chars = 0
        per_point = []
        for evid, rs in by.items():
            facts, seen = [], set()
            outs = []
            for r in rs:
                for c in ev.clauses(r['factsText']):
                    c = ce.clean(c)
                    if len(c) > 4 and '做的事' not in c and '玩家这回合' not in c and c not in seen:
                        seen.add(c)
                        facts.append(c)
                for x in r['resultLines']:
                    p = parse_result(x)
                    if p and p['outcome']:
                        outs.append(p)
            if arm == 'current-1.7b':
                # 回合正文被四个 point 各记一遍，每回合只算一次
                seen_turns, parts = set(), []
                for r in rs:
                    if r['turnId'] in seen_turns:
                        continue
                    seen_turns.add(r['turnId'])
                    parts.append(r['systemProse'] or '')
                text = ''.join(parts)
            else:
                text = ''.join(text_of(arm, r) for r in rs)
            grams = ev.bigrams(text)
            hit_f += sum(1 for c in facts if ev.coverage(c, grams) >= 0.5)
            tot_f += len(facts)
            chars += len(text)
            for p in outs:
                cue = ev.FAIL_CUE if p['outcome'] in ('没有成功', '无法完成', '失败') else (
                    ev.PART_CUE if p['outcome'] in ('只完成一部分', '部分成功') else None)
                if not cue:
                    continue
                tot_o += 1
                if any(cue.search(s) for s in ev.sentences(text) if p['actor'] in s):
                    hit_o += 1
        for r in rows:
            if arm == 'current-1.7b':
                ts = turn_stats[(r['evidence'], r['turnId'])]
                per_point.append({'id': r['id'], 'chars': ts['chars'] / ts['n'],
                                  'sentences': ts['sent'] / ts['n']})
            else:
                t = text_of(arm, r)
                per_point.append({'id': r['id'], 'chars': len(t), 'sentences': len(ev.sentences(t))})
        report[arm] = {
            'cumulativeFactCover': round(hit_f / max(1, tot_f), 3),
            'cumulativeFacts': f'{hit_f}/{tot_f}',
            'cumulativeOutcome': round(hit_o / max(1, tot_o), 3),
            'cumulativeOutcomes': f'{hit_o}/{tot_o}',
            'cumulativeChars': chars,
            'charsPerPoint': round(sum(p['chars'] for p in per_point) / len(per_point), 1),
            'sentencesPerPoint': round(sum(p['sentences'] for p in per_point) / len(per_point), 1),
        }
    (HERE / 'evaluate-arms.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf8')
    for k, v in report.items():
        print(k, json.dumps(v, ensure_ascii=False))


if __name__ == '__main__':
    main()
