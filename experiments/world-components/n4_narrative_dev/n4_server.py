"""Resident u240 process: load once, serve many rounds over stdin/stdout JSONL.

Protocol (one line each way):

    in : {"roundId": "train-r1", "payload": {...same as mixed-round-authorized.json...}}
    out: {"roundId": "...", "result": {...pipeline result...}, "timing": {...}}

Cold start is the model load, reported once in ``{"type": "ready", ...}``.
Hot time is per-round generation. Everything is wall-clock on the same box, so
cold + hot is directly comparable with a batch run.
"""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import fact_contract as FC  # noqa: E402
import n4_pipeline as P  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ckpt', required=True)
    parser.add_argument('--budget', type=float, default=20.0)
    args = parser.parse_args()

    started = time.perf_counter()
    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tokenizer = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.ckpt, torch_dtype=torch.float32)
    model.to('cuda' if torch.cuda.is_available() else 'cpu').eval()
    cold = round(time.perf_counter() - started, 3)
    print(json.dumps({'type': 'ready', 'coldStartSeconds': cold,
                      'device': 'cuda' if torch.cuda.is_available() else 'cpu'}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request_started = time.perf_counter()
        message = json.loads(line)
        round_id = message['roundId']
        payload = message['payload']
        units = payload['units']
        for unit in units:
            unit.setdefault('worldId', payload['worldId'])

        read_started = time.perf_counter()
        rows = P.generate(model, tokenizer, torch, units, args.budget)
        generate_seconds = round(time.perf_counter() - read_started, 3)

        incomplete = [row['factId'] for row in rows if not row['complete']]
        verdict = payload['authorization']
        if incomplete:
            verdict = dict(verdict)
            verdict['relations'] = [r for r in verdict['relations']
                                    if not ({r['fromFactId'], r['toFactId']} & set(incomplete))]

        edit_started = time.perf_counter()
        edited = P.two_layer_edit(rows, verdict,
                                  {u['name'] for u in units
                                   if str(u.get('entityId', '')).startswith(('person_', 'char_'))})
        edit_seconds = round(time.perf_counter() - edit_started, 3)

        result = {
            'pipeline': P.PIPELINE_VERSION,
            'components': {'validator': P.VALIDATOR, 'relationEdit': P.RELATION_VERSION,
                           'conservativeEdit': P.EDIT_VERSION},
            'roundId': round_id, 'worldId': payload['worldId'],
            'original': ''.join(u['text'] for u in units),
            'generation': rows,
            'authorization': verdict,
            'incompleteFacts': incomplete,
            'sourceComplete': not incomplete,
            'edit': edited, 'edited': edited['text'],
            'timing': {'generate': generate_seconds, 'edit': edit_seconds,
                       'requestTotal': round(time.perf_counter() - request_started, 3)},
        }
        print(json.dumps({'roundId': round_id, 'result': result}, ensure_ascii=False),
              flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
