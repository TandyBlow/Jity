"""离线解码对照：A 贪心（现有实现） vs B 束宽 2。

B 的约束：
  * 按累计对数概率选输出，**不加长度奖励、不加重复惩罚、不做禁词、不做事实过滤**；
  * 遇到 EOS 结束；不设长度上限（只由 20 秒预算与 EOS 决定）；
  * 与 A 共用同一输入文本、同一预算。

入口只读冻结的案例清单，不触碰常驻服务。
"""
import argparse
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from component_paths import PATHS  # noqa: E402
import fact_contract as FC  # noqa: E402
from sequence_policy import generate_greedy  # noqa: E402

SAFETY_TOKENS = 256          # 仅防死循环，命中会显式标记 truncated


def _ids(model):
    config = model.generation_config
    start = config.decoder_start_token_id
    if start is None:
        start = model.config.decoder_start_token_id
    eos = config.eos_token_id
    if eos is None:
        eos = model.config.eos_token_id
    eos_set = {eos} if isinstance(eos, int) else set(eos)
    return start, eos_set


def generate_beam(model, encoded, width=2, timeout_seconds=20.0):
    """Beam search by cumulative log-probability. No length/repetition shaping."""
    import torch

    model.eval()
    start, eos_set = _ids(model)
    started = time.perf_counter()
    beams = [([start], 0.0)]
    finished = []
    steps = 0
    truncated = False
    with torch.inference_mode():
        while time.perf_counter() - started < timeout_seconds:
            if not beams:
                break
            candidates = []
            for tokens, score in beams:
                decoder = torch.tensor([tokens], dtype=torch.long,
                                       device=encoded['input_ids'].device)
                out = model(input_ids=encoded['input_ids'],
                            attention_mask=encoded.get('attention_mask'),
                            decoder_input_ids=decoder, return_dict=True)
                logp = torch.log_softmax(out.logits[0, -1, :].float(), dim=-1)
                top_values, top_index = logp.topk(width)
                for rank in range(width):
                    candidates.append((tokens + [int(top_index[rank])],
                                       score + float(top_values[rank])))
            steps += 1
            candidates.sort(key=lambda item: -item[1])
            beams = []
            for tokens, score in candidates:
                if tokens[-1] in eos_set:
                    finished.append((tokens, score))
                else:
                    beams.append((tokens, score))
                if len(beams) == width:
                    break
            # 无长度奖励时累计对数概率随延长单调下降：最好未完成已经不可能
            # 超过最差已完成，就可以停（标准停止条件，不引入任何长度塑形）。
            if len(finished) >= width and (
                    not beams or max(score for _, score in beams)
                    <= min(score for _, score in finished)):
                break
            if steps >= SAFETY_TOKENS:
                truncated = True
                break
    seconds = round(time.perf_counter() - started, 3)
    if finished:
        tokens, score = max(finished, key=lambda item: item[1])
        complete = True
    elif beams:
        tokens, score = max(beams, key=lambda item: item[1])
        complete = False
    else:
        tokens, score = [start], float('-inf')
        complete = False
    return tokens, {'complete': complete, 'steps': steps, 'candidates': len(finished),
                    'seconds': seconds, 'truncated': truncated,
                    'score': round(score, 4)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', '--ckpt', dest='ckpt', default=None)
    parser.add_argument('--cases', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--budget', type=float, default=20.0)
    parser.add_argument('--width', type=int, default=2)
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()
    args.ckpt = str(PATHS.model(args.ckpt))
    args.cases = str(PATHS.input(args.cases))
    args.out = str(PATHS.output(args.out))
    pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)

    import torch
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    payload = json.loads(pathlib.Path(args.cases).read_text(encoding='utf-8'))
    cases = payload['cases'][:args.limit] if args.limit else payload['cases']
    FC.check_units([{'unitId': c['caseId'], 'kind': c['kind'], 'input': c['input']}
                    for c in cases])

    tokenizer = T5Tokenizer.from_pretrained(args.ckpt, legacy=False, local_files_only=True)
    model = T5ForConditionalGeneration.from_pretrained(args.ckpt, torch_dtype=torch.float32)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model.to(device).eval()

    rows = []
    for case in cases:
        encoded = tokenizer(case['input'], return_tensors='pt',
                            truncation=False).to(device)
        greedy_ids, greedy_meta = generate_greedy(model, encoded, args.budget)
        beam_ids, beam_meta = generate_beam(model, encoded, args.width, args.budget)
        rows.append({'caseId': case['caseId'], 'source': case['source'],
                     'group': case.get('group'), 'kind': case['kind'],
                     'name': case['name'], 'factText': case['factText'],
                     'greedy': {'text': tokenizer.decode(greedy_ids[0],
                                                          skip_special_tokens=True),
                                'complete': bool(greedy_meta['complete']),
                                'steps': int(greedy_meta.get('newTokens') or 0),
                                'seconds': round(float(greedy_meta['seconds']), 3)},
                     'beam': {'text': tokenizer.decode(beam_ids,
                                                       skip_special_tokens=True),
                              'complete': beam_meta['complete'],
                              'steps': beam_meta['steps'],
                              'seconds': beam_meta['seconds'],
                              'candidates': beam_meta['candidates'],
                              'truncated': beam_meta['truncated'],
                              'score': beam_meta['score']}})
        print(json.dumps({'case': case['caseId'], 'greedy': rows[-1]['greedy']['text'],
                          'beam': rows[-1]['beam']['text']}, ensure_ascii=False), flush=True)

    summary = {'width': args.width, 'budget': args.budget, 'cases': len(rows),
               'greedySeconds': round(sum(r['greedy']['seconds'] for r in rows), 2),
               'beamSeconds': round(sum(r['beam']['seconds'] for r in rows), 2),
               'greedyComplete': sum(1 for r in rows if r['greedy']['complete']),
               'beamComplete': sum(1 for r in rows if r['beam']['complete']),
               'greedySteps': sum(r['greedy']['steps'] for r in rows),
               'beamSteps': sum(r['beam']['steps'] for r in rows),
               'beamTruncated': sum(1 for r in rows if r['beam']['truncated'])}
    pathlib.Path(args.out).write_text(json.dumps({'summary': summary, 'rows': rows},
                                                 ensure_ascii=False, indent=1),
                                      encoding='utf-8')
    print('SUMMARY', json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
