"""Generate the finite pre-training review sheet and structural/semantic flags.

This is an assistant re-read ("复看"), not an independent human gold label.
"""
from __future__ import annotations
import json, pathlib, re, sys
from collections import defaultdict

ROOT = pathlib.Path('D:/others/Jity')
PAIRS = ROOT / 'artifacts' / 'statement-verification' / 'pairs-v1.jsonl'
REGRESSION = ROOT / 'artifacts' / 'statement-verification' / 'regression-v1.jsonl'
OUT = ROOT / 'artifacts' / 'statement-verification' / 'review-v1.jsonl'
OUT_MD = ROOT / 'artifacts' / 'statement-verification' / 'review-v1.md'


def grams(t):
    t = re.sub(r"[\s，,。．.；;：:！!？?、…—－\-'\"“”‘’（）()《》「」]", '', t or '')
    return {t[i:i + 2] for i in range(len(t) - 1)}


def overlap(a, b):
    ga, gb = grams(a), grams(b)
    return len(ga & gb) / max(1, len(ga))


def source_ids(r):
    return {x['sourceId'] for x in r.get('facts', [])} | {x['sourceId'] for x in r.get('scene', [])} | {x['sourceId'] for x in r.get('visible', [])}


def flags(r, by_pair):
    out = []
    if r['candidateText'] not in r['fullText']:
        out.append('candidate-not-in-text')
    ids = source_ids(r)
    for gid in r.get('goldSourceIds', []):
        if gid not in ids:
            out.append(f'gold-missing:{gid}')
    if r['label'] == 'unsupported':
        for f in r.get('facts', []):
            if f.get('name') and f['name'] in r['candidateText'] and f.get('factText') == r.get('candidateText'):
                out.append(f'exact-candidate-fact:{f["sourceId"]}')
            if f.get('factText') and f['factText'] in r['candidateText']:
                out.append(f'fact-substring:{f["sourceId"]}')
        if r['origin'] == 'n5-derived':
            sup = next((x for x in by_pair[r['pairId']] if x['label'] == 'supported'), None)
            if sup:
                rem = r.get('removedFactId')
                rf = next((f for f in sup['facts'] if f['sourceId'] == rem), None)
                if rf:
                    for f in r.get('facts', []):
                        if f.get('name') == rf.get('name') and f.get('factText') == rf.get('factText'):
                            out.append(f'residual-exact-fact:{f["sourceId"]}')
                        o = overlap(r['candidateText'], f.get('factText', ''))
                        if o >= 0.5:
                            out.append(f'residual-overlap:{f["sourceId"]}:{o:.2f}')
    if r['label'] == 'supported' and not r.get('goldSourceIds'):
        out.append('supported-without-gold')
    return out


def main():
    rows = [json.loads(l) for l in PAIRS.read_text(encoding='utf-8').splitlines() if l.strip()]
    reg = [json.loads(l) for l in REGRESSION.read_text(encoding='utf-8').splitlines() if l.strip()]
    by_pair = defaultdict(list)
    for r in rows:
        by_pair[r['pairId']].append(r)
    selected = []
    # confirm: all
    selected += [r for r in rows if r['split'] == 'confirm']
    # train/dev: all four targeted categories
    selected += [r for r in rows if r['split'] in ('train', 'dev') and r['category'] in
                 ('body', 'background', 'visible-state', 'extra-action')]
    # general sample: 20 pairs from train + 20 pairs from dev (both labels)
    for split in ('train', 'dev'):
        pids = sorted({r['pairId'] for r in rows if r['split'] == split and r['category'] == 'general'})
        # deterministic spread over the sorted list
        idxs = [round(i * (len(pids) - 1) / 19) for i in range(20)] if len(pids) >= 20 else list(range(len(pids)))
        chosen = {pids[i] for i in idxs}
        selected += [r for r in rows if r['split'] == split and r['pairId'] in chosen]
    # de-duplicate by exampleId
    selected = list({r['exampleId']: r for r in selected}.values())
    selected.sort(key=lambda r: (r['split'], r['origin'], r['pairId'], r['exampleId']))
    with OUT.open('w', encoding='utf-8') as f:
        for r in selected:
            rec = dict(r)
            rec['reviewFlags'] = flags(r, by_pair)
            rec['reviewer'] = 'assistant (same model), 复看，not independent human gold'
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    # markdown compact sheet
    lines = ['# 训练前复看表（assistant 复看，不是独立人工金标）', '',
             f'- examples: {len(selected)}',
             f'- confirm: {sum(1 for r in selected if r["split"]=="confirm")}',
             f'- train/dev targeted: {sum(1 for r in selected if r["split"] in ("train","dev") and r["category"] in ("body","background","visible-state","extra-action"))}',
             f'- general sample: {sum(1 for r in selected if r["category"]=="general")}',
             '', '## Flags', '']
    flagged = [r for r in selected if flags(r, by_pair)]
    lines += [f'- {r["exampleId"]}: {"; ".join(flags(r, by_pair))}' for r in flagged] or ['- none']
    lines += ['', '## Items', '']
    for r in selected:
        facts = '；'.join(f"{f['sourceId']}={f['factText']}" for f in r.get('facts', [])) or '无'
        scene = '；'.join(f"{s['sourceId']}={s['text']}" for s in r.get('scene', [])) or '无'
        vis = '；'.join(f"{v['sourceId']}={v['text']}" for v in r.get('visible', [])) or '无'
        lines += [f"### {r['exampleId']}", f"- split/category: {r['split']} / {r['category']} / {r['pairMode']}",
                  f"- label: **{r['label']}**; gold: {r.get('goldSourceIds')}",
                  f"- full: {r['fullText']}", f"- candidate: {r['candidateText']}",
                  f"- facts: {facts}", f"- scene: {scene}", f"- visible: {vis}",
                  f"- flags: {'; '.join(flags(r, by_pair)) or 'none'}", '']
    OUT_MD.write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'selected': len(selected),
                      'confirm': sum(1 for r in selected if r['split'] == 'confirm'),
                      'targeted': sum(1 for r in selected if r['split'] in ('train','dev') and r['category'] in ('body','background','visible-state','extra-action')),
                      'general': sum(1 for r in selected if r['category'] == 'general'),
                      'flagged': len(flagged),
                      'flagCounts': {k: sum(1 for r in selected for x in flags(r, by_pair) if x.startswith(k)) for k in ['candidate-not-in-text','gold-missing','exact-candidate-fact','fact-substring','residual-exact-fact','residual-overlap','supported-without-gold']}},
                     ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
