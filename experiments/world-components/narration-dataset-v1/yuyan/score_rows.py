"""Score generated narration on what we actually care about, not token CE.

For each holdout row:
  * generate one greedy and one sampled narration from X;
  * check FACT ALIGNMENT against the row's recorded changes:
      - every changed person / item / location must be named in the text;
      - no character name may appear that is not in X (invented person);
      - the task goal / personality text must not be quoted verbatim;
      - meta words (任务/精神值/个性/外貌) must not appear in prose;
      - a completed task must be narrated as done, not as still pending;
  * measure STYLE (paragraphs, dialogue share, sentence length, repetition);
  * measure SELF-CE (model's own per-token CE on its own output) and
    ORACLE-CE (best of N sampled outputs against the human reference).

The point: CE against one human reference cannot separate a correct narration
from a factually wrong one (ce_probe.py shows 1.9351 vs 1.9669), so it must not
be the number we select checkpoints by.

Usage:
  python -X utf8 score_rows.py --adapter lora.pt --rows rows-yuyan.jsonl \
      --holdout row-0010,row-0017 --out report.json
"""
import argparse
import io
import json
import os
import statistics
import sys

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import train_yuyan as T  # noqa: E402

META_WORDS = ["任务", "精神值", "个性", "外貌", "状态", "视角"]
COMPLETION_MARKERS = ["完成", "做完", "查完", "写好", "记下", "交出去", "算完"]


import re  # noqa: E402


def paragraphs(text):
    return [p for p in text.split("\n\n") if p.strip()]


def sentence_count(text):
    return len([s for s in re.split(r"[。！？…]+", text) if s.strip()])


def generate(model, prompt_ids, index, tokens, eos, max_new, temperature, seed, device):
    if temperature:
        torch.manual_seed(seed)
    x = torch.tensor([list(prompt_ids)], device=device)
    model.eval()
    with torch.no_grad():
        for _ in range(max_new):
            logits = model(x[:, -2048:])[0, -1].clone()
            logits[eos] = -1e9
            if temperature == 0:
                nxt = int(logits.argmax())
            else:
                probs = torch.softmax(logits / temperature, dim=-1)
                nxt = int(torch.multinomial(probs, 1))
            x = torch.cat([x, torch.tensor([[nxt]], device=device)], dim=1)
    text = ''.join(tokens[i] for i in x[0, len(prompt_ids):].tolist())
    return text.replace(T.PARA_MARK, '\n\n')


def alignment(row, text):
    x = json.loads(row["xJson"])
    people = x["上回合状态"]["人物"]
    items = x["上回合状态"].get("物品", {})
    changes = x["本回合变化"]["变化"]
    problems = []

    for entity in changes:
        if entity not in text:
            problems.append(f"变化对象未出现:{entity}")

    # a speaker name at the start of a clause that the state does not contain
    known = set(people) | set(items) | set(changes)
    stop = {'我', '你', '他', '她', '它', '我们', '你们', '他们', '有人', '那人',
            '一个人', '两个人', '三个'}
    for line in text.splitlines():
        for match in re.finditer(r"[一-龥]{2,3}(?=说|问|道|笑)", line):
            candidate = match.group(0)
            before = line[match.start() - 1] if match.start() else "「"
            if before not in "「，。！？、：；「":
                continue
            if candidate in known or candidate in stop:
                continue
            problems.append('疑似新增人物:' + candidate)

    for word in META_WORDS:
        if word in text:
            problems.append(f"状态词入文:{word}")

    for name, spec in people.items():
        goal = spec.get("任务", {}).get("大任务", {}).get("目标")
        if goal and goal in text:
            problems.append("照抄任务说明")
        for trait in spec.get("个性", []):
            if len(trait) >= 6 and trait in text:
                problems.append(f"照抄个性:{trait[:8]}")

    for entity, spec in changes.items():
        if "完成任务" in spec:
            if not any(marker in text for marker in COMPLETION_MARKERS):
                problems.append(f"完成任务未写成已完成:{entity}")

    return sorted(set(problems))


def style(text):
    paras = paragraphs(text)
    dialogue = [p for p in paras if p.startswith("「")]
    sents = sentence_count(text)
    chars = len(text.replace("\n", ""))
    repeat = 0
    for n in (8,):
        grams = [text[i:i + n] for i in range(max(len(text) - n, 0))]
        seen = {}
        for gram in grams:
            seen[gram] = seen.get(gram, 0) + 1
        repeat = max(seen.values()) if seen else 0
    return {
        "chars": chars,
        "paras": len(paras),
        "median_para": statistics.median([len(p) for p in paras]) if paras else 0,
        "dialogue_share": round(len(dialogue) / len(paras), 2) if paras else 0,
        "mean_sentence": round(chars / sents, 1) if sents else 0,
        "max_repeat_8gram": repeat,
    }


def per_token_ce(model, ids, prompt_len, device):
    x = torch.tensor([ids[:-1]], device=device)
    labels = torch.tensor([[-100] * (prompt_len - 1) + ids[prompt_len:]], device=device)
    with torch.no_grad():
        logits = model(x)
    mask = labels[0] != -100
    if mask.sum() == 0:
        return float("nan")
    logp = torch.log_softmax(logits[0].float()[mask], dim=-1)
    picked = logp.gather(1, labels[0][mask].unsqueeze(1)).squeeze(1)
    return float(-picked.mean())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="checkpoint_best.pt")
    ap.add_argument("--dict", default="dict.txt")
    ap.add_argument("--adapter", default="")
    ap.add_argument("--rows", default="rows-yuyan.jsonl")
    ap.add_argument("--holdout", default="row-0010,row-0017")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--max-new", type=int, default=420)
    ap.add_argument("--out", default="score.json")
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tokens = T.load_vocab(args.dict)
    index = {c: i for i, c in enumerate(tokens)}
    eos = index["</s>"]

    ck = T.load_checkpoint(args.base)
    model, shape = T.build_from_state(ck["model"], heads=20)
    del ck
    model = model.to(device)
    if args.adapter:
        model = T.apply_lora(model, args.rank, args.alpha).to(device)
        adapter = torch.load(args.adapter, map_location="cpu", weights_only=True)
        own = dict(model.named_parameters())
        with torch.no_grad():
            for name, tensor in adapter.items():
                own[name].copy_(tensor.to(device))
    model.eval()

    rows = [json.loads(line) for line in io.open(args.rows, encoding="utf-8")]
    wanted = {v.strip() for v in args.holdout.split(",")}
    picked = [r for r in rows if r["id"] in wanted]

    results = []
    for row in picked:
        prompt = T.encode(row["xProse"], index)
        reference = row["yMarked"]
        greedy = generate(model, prompt, index, tokens, eos, args.max_new, 0.0, 0, device)
        samples = [generate(model, prompt, index, tokens, eos, args.max_new,
                            0.85, 100 + i, device)
                   for i in range(args.samples)]

        oracle = []
        for text in samples:
            norm = text.replace("\n\n", T.PARA_MARK).replace("\n", "")
            ids = prompt + T.encode(norm, index) + [eos]
            oracle.append(per_token_ce(model, ids, len(prompt), device))
        ref_ids = prompt + T.encode(reference, index) + [eos]
        ref_ce = per_token_ce(model, ref_ids, len(prompt), device)
        greedy_ids = prompt + T.encode(greedy.replace("\n\n", T.PARA_MARK).replace("\n", ""), index) + [eos]
        self_ce = per_token_ce(model, greedy_ids, len(prompt), device)

        entry = {
            "id": row["id"],
            "reference_ce": round(ref_ce, 4),
            "oracle_ce_best_of_n": round(min(oracle), 4),
            "self_ce_greedy": round(self_ce, 4),
            "greedy": greedy,
            "alignment_greedy": alignment(row, greedy),
            "style_greedy": style(greedy),
            "alignment_samples": [alignment(row, s) for s in samples],
            "style_samples": [style(s) for s in samples],
        }
        results.append(entry)
        print(f"{row['id']}: refCE {entry['reference_ce']:.4f} "
              f"oracleCE {entry['oracle_ce_best_of_n']:.4f} "
              f"selfCE {entry['self_ce_greedy']:.4f} "
              f"问题 {len(entry['alignment_greedy'])} 项 "
              f"段 {entry['style_greedy']['paras']} "
              f"对话 {entry['style_greedy']['dialogue_share']}", flush=True)
        for problem in entry["alignment_greedy"]:
            print(f"    - {problem}", flush=True)

    with io.open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"rows": results}, handle, ensure_ascii=False, indent=1)
    clean = sum(1 for r in results if not r["alignment_greedy"])
    print(f"\n贪心输出无问题 {clean}/{len(results)}")
    print(f"平均参照CE {statistics.mean(r['reference_ce'] for r in results):.4f}"
          f" | 平均 oracleCE {statistics.mean(r['oracle_ce_best_of_n'] for r in results):.4f}"
          f" | 平均 selfCE {statistics.mean(r['self_ce_greedy'] for r in results):.4f}")


if __name__ == "__main__":
    main()
