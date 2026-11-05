"""Judge calibration: run the mechanical judge over the ARCHIVED diagnostic
outputs and put its numbers next to the verdicts recorded in the design docs.

This does not re-decide the archive; it shows how far the mechanical judge is
from the recorded human reading, so the A/B deltas can be read with that bias
in view.
"""
from __future__ import annotations
import json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ART = ROOT / 'artifacts' / 'world-components'
# Historical archives live in the main worktree; they are not part of
# this commit. The committed calibration JSON is the record of the run.
WP = ROOT.parents[1] / 'artifacts' / 'world-provenance'
OUT = ART / 'route-split-judge-calibration-v1.json'
sys.path.insert(0, str(HERE))
import judge_expression as J  # noqa: E402

UNITS = {}
for fn in ('n4-final24-contract.jsonl', 'n4-cf24-contract.jsonl',
           'n4-object18-contract.jsonl', 'n4-expand36-contract.jsonl'):
    for l in (ART / fn).read_text(encoding='utf-8').splitlines():
        if l.strip():
            u = json.loads(l)
            UNITS[u['unitId']] = u

ARCHIVES = {
    'diag2-v2best': {'file': 'diag2-v2best.json',
                     'historicalRecorded': {
                         'criterion': 'continuous-fragment pass count',
                         'value': '202/215',
                         'humanSemanticGold': False,
                         'note': '7 definite unsupported + 6 pending review '
                                 '(boundary-arm-closing-record.md 1.1); this is not a '
                                 'human semantic gold label'}},
    'diag-b240': {'file': 'diag-b240.json',
                  'checkpointAttribution': 'unconfirmed',
                  'usableAsU240Control': False,
                  'note': 'the filename says b240, while two units read 玻璃罩; the output '
                          'signature does not uniquely identify a checkpoint and the source '
                          'conflict is unresolved. Do not use this archive as the u240 '
                          'control.'},
    'diag-b': {'file': 'diag-b.json',
               'checkpointAttribution': 'archive filename only',
               'note': 'baseline arm archive; no independent identity check in this round'},
}



def main():
    out = {'version': 'route-split-judge-calibration-v1', 'created': '2026-11-05',
           'judge': 'judge_expression.py (vocabulary-driven, mechanical)',
           'rows': {}}
    for name, meta in ARCHIVES.items():
        d = json.loads((WP / meta['file']).read_text(encoding='utf-8'))
        res = []
        for setname, rs in d.items():
            if not isinstance(rs, list):
                continue
            for r in rs:
                u = UNITS.get(r['unitId'])
                if u:
                    res.append(J.judge_unit_row(u, r['text']))
        out['rows'][name] = {'file': meta['file'],
                             **{k: v for k, v in meta.items() if k != 'file'},
                             'mechanical': J.summarize(res)}
    out['historicalRowsAreNotControls'] = True
    out['reading'] = [
        'the mechanical judge is a vocabulary-bounded screen, not a human semantic '
        'gold standard; its own false positives and false negatives are known',
        'the v2-best historical number is a continuous-fragment pass count '
        '(202/215), not 202 human-verified facts',
        'diag-b240 has no confirmed checkpoint identity: 玻璃罩 appears in two units '
        'but is not unique to u240, and the filename/source conflict is unresolved',
        'the diag-b240 mechanical row is retained only to show judge behaviour; it is '
        'not the u240 control and is not used in the A/B conclusion',
        'this calibration is sufficient to show the judge bias; no further '
        'calibration round is run here',
        'A/B differences are reported per metric with the flagged lists attached for '
        'manual reading, and the clean total is not used to declare a winner',
    ]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(out['rows'], ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
