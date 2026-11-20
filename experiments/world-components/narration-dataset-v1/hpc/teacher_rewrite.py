# -*- coding: utf-8 -*-
"""Rewrite the 199 yuyan scenes under the row's settled facts.

The 7B rewrite is only a teacher. Every output still goes through
factcheck_yuyan.py; rejected sentences are dropped and missing position/task
changes are added back as plain factual sentences. The resulting target is
what the browser-sized model is trained on.
"""
import argparse
import json
import os
import re
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from factcheck_yuyan import check, parse, split_sentences


def visible_names(row):
    _, _, _, _, chars, _, locs, after, _, _, view = parse(row)
    pos = {n: after[n].get("位置") for n in chars}
    return [n for n in chars if pos.get(n) == pos.get(view)], view


def prompt_for(row):
    x = json.loads(row["xJson"])
    visible, view = visible_names(row)
    facts = row["xProse"]
    return f"""你是中文小说编辑。下面给出这一回合已经结算的事实和一段旧稿。请把旧稿改写成 350 到 650 字的小说正文。

要求：
1. 保留旧稿的叙述语气、生活细节、对话和分段；
2. 删除或改写所有事实不支持的人物、地点、物品、事件、数字、任务完成和心理判断；
3. 只能使用事实里出现的人物、地点、物品；人物位置、任务完成、精神值、时间必须与【本回合变化】一致；
4. 只写主角附近的人，不在主角所在地点的人不要写进来；主角是「{view}」，在场人物是「{'、'.join(visible)}」；
5. 不写字段名、状态列表、标题或解释；不新增枪声、敲门声、发现线索、摔倒、追逐等事件；
6. 可以写环境、动作、对话和短暂的内心，但必须由事实支撑。

【事实】
{facts}

【旧稿】
{row['yPlain']}

【改写正文】
"""


def add_missing(row, filtered, result):
    """Append the plain fact sentence for a change the rewrite failed to state."""
    _, before, _, _, chars, _, _, after, _, delta, view = parse(row)
    out = filtered
    for item in result.get("missing", []):
        if item.startswith("position:"):
            name, loc = item.split(":", 1)[1].split("->", 1)
            old = (chars.get(name) or {}).get("位置") or ""
            out += f"{name}从{old}走到{loc}。" if old else f"{name}走到{loc}。"
        elif item.startswith("task:"):
            goal = item.split(":", 1)[1]
            owner = None
            for name, value in delta.items():
                if isinstance(value, dict) and goal in (value.get("完成任务") or []):
                    owner = name
                    break
            out += f"{owner or view}完成了「{goal}」。"
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="rows-yuyan.jsonl")
    parser.add_argument("--model", default=os.path.expanduser("~/qwen7b"))
    parser.add_argument("--out", default="teacher-outputs.jsonl")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch", type=int, default=3)
    parser.add_argument("--max-new", type=int, default=1100)
    args = parser.parse_args()

    rows = [json.loads(line) for line in open(args.data, encoding="utf-8")]
    if args.limit:
        rows = rows[:args.limit]
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        args.model, torch_dtype=torch.bfloat16, trust_remote_code=True).to("cuda")
    model.eval()
    started = time.time()
    done = 0
    with open(args.out, "w", encoding="utf-8") as handle, torch.inference_mode():
        for start in range(0, len(rows), args.batch):
            chunk = rows[start:start + args.batch]
            prompts = [prompt_for(row) for row in chunk]
            chats = [tokenizer.apply_chat_template(
                [{"role": "system", "content": "你是中文小说编辑，只按给定事实改写。"},
                 {"role": "user", "content": prompt}],
                tokenize=False, add_generation_prompt=True) for prompt in prompts]
            inputs = tokenizer(chats, return_tensors="pt", padding=True, truncation=True, max_length=6144).to(model.device)
            generated = model.generate(
                **inputs, max_new_tokens=args.max_new, do_sample=True,
                temperature=0.7, top_p=0.9, repetition_penalty=1.05,
                eos_token_id=tokenizer.eos_token_id, pad_token_id=tokenizer.pad_token_id)
            texts = tokenizer.batch_decode(generated[:, inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            for row, raw in zip(chunk, texts):
                raw = raw.strip()
                result = check(row, raw)
                filtered = "".join(result["kept"])
                if result["missing"]:
                    filtered = add_missing(row, filtered, result)
                record = {
                    "id": row["id"],
                    "raw": raw,
                    "filtered": filtered,
                    "ok": result["ok"],
                    "kept": len(result["kept"]),
                    "sentences": len(split_sentences(raw)),
                    "violations": result["violations"][:8],
                    "missing": result["missing"],
                    "rawChars": len(raw),
                    "filteredChars": len(filtered),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                handle.flush()
                done += 1
            elapsed = time.time() - started
            print(f"{done}/{len(rows)} {elapsed/done:.1f}s/row", flush=True)
    print(f"done {done} in {time.time()-started:.0f}s")


if __name__ == "__main__":
    main()
