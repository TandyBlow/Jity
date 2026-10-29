# N2 content-selection runner (round 18, first comparison round).
#
# Task: given a committed fact table (numbered) and a viewpoint rule, decide
# which fact ids go into the narration. The output is a selection, never new
# world facts: unknown ids are invalid, and the judge checks coverage of the
# must set plus POV-forbidden selections.
#
# Arms (same inputs, same judge):
#   P0 program-select-all  - selects every fact (the trivial "no selection"
#                            behaviour the plan forbids as a final capability)
#   P1 program-rule        - selects must + facts whose entity is visible from
#                            the viewpoint (drops forbidden, keeps omittable)
#   M1a randeng-zero-shot  - Randeng-T5-77M base, instruction AFTER the data
#   M1b randeng-answer-slot- same model, instruction BEFORE the data and an
#                            explicit 「编号：」 answer prefix (prompt-shape
#                            operation point; parsing keeps only the answer)
#
# Judge (program, fixed before running):
#   mustRecall       = |must ∩ sel| / |must|                  hard: 1.0
#   forbiddenHits    = |forbidden ∩ sel|                      hard: 0
#   precision/recall/F1 vs the program-defined target
#   selectAll        = sel ⊇ all facts (recorded, never required)
#   pass             = mustRecall == 1 and forbiddenHits == 0 and F1 >= 0.6
#                      (0.6 is a FIRST-ROUND dev threshold, not a frozen gate)
#
# Usage: python experiments/world-components/n2_selection/run_n2.py \
#          [--skip-model] [--variants a,b]
# Output: artifacts/world-components/n2-selection-r1.json

import hashlib
import importlib.machinery
import json
import pathlib
import re
import sys
import time
import types

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent
ITEMS = HERE / "items.jsonl"
ASSETS = HERE.parent / "assets"
BASE_MODEL = ASSETS / "randeng-t5-77m"
REPORT = REPO / "artifacts" / "world-components" / "n2-selection-r1.json"

F1_GATE = 0.6          # first-round dev threshold (not a frozen acceptance gate)
MAX_NEW = 32


def sha_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_items() -> list:
    return [json.loads(line) for line in
            ITEMS.read_text(encoding="utf-8").splitlines() if line.strip()]


def fact_line(i: int, f: dict) -> str:
    k = f["kind"]
    if k == "moved":
        return f"{i}. 位置：{f['name']} 从{f['from']}到{f['to']}"
    if k == "task_achieved":
        return f"{i}. 任务达成：{f['name']}「{f['goal']}」"
    if k == "personality_changed":
        return f"{i}. 个性：{f['name']}{f['text']}"
    if k == "sanity_changed":
        d = "上升" if f["to"] > f["from"] else "下降" if f["to"] < f["from"] else "不变"
        return f"{i}. 理智：{f['name']} {f['from']}→{f['to']}（{d}）"
    if k == "appearance_changed":
        return f"{i}. 外貌：{f['name']} {f['text']}"
    if k == "positioned_at":
        return f"{i}. 现状：{f['name']} 已在{f['at']}"
    if k == "time":
        return f"{i}. 时间推进：约{f['amount']}分钟"
    if k == "no_change":
        return f"{i}. 无变化：{f.get('scope', '全局')}"
    raise ValueError(f"unknown fact kind {k}")


def prompt_for(item: dict, variant: str = "a") -> str:
    v = item["viewpoint"]
    lines = [fact_line(i + 1, f) for i, f in enumerate(item["facts"])]
    body = ("叙事选材任务。\n"
            f"视角：{v['rule']}。\n"
            "事实：\n" + "\n".join(lines) + "\n")
    if variant == "a":
        return (body
                + "任务：选出必须写进正文的事实编号，视角看不到的不要选。\n"
                + "只输出编号，用逗号分隔。")
    if variant == "b":
        return ("选材。只输出要写进正文的事实编号。\n" + body + "编号：")
    raise ValueError(variant)


ANSWER_MARKERS = ("编号：", "编号:", "答案：", "答案:")


def parse_ids(text: str, n_facts: int, answer_only: bool = False) -> tuple:
    """Model output -> (selected 1-based ids that exist, invalid tokens).
    answer_only keeps only the part after an answer marker, so an echo of the
    numbered fact list is not counted as a selection (arm b)."""
    if answer_only:
        for marker in ANSWER_MARKERS:
            if marker in text:
                text = text.rsplit(marker, 1)[1]
                break
    stripped = re.sub(r"[，、;；\s]+", ",", text.strip())
    sel, bad = set(), []
    for tok in re.split(r"[,\n]+", stripped):
        tok = tok.strip().strip("。.")
        if not tok:
            continue
        m = re.fullmatch(r"(?:f|F|事实)?(\d{1,2})", tok)
        if not m:
            bad.append(tok[:16])
            continue
        v = int(m.group(1))
        if 1 <= v <= n_facts:
            sel.add(v)
        else:
            bad.append(tok[:16])
    return sel, bad


def judge(item: dict, sel1: set, bad: list) -> dict:
    facts = item["facts"]
    id_of = {i + 1: f["factId"] for i, f in enumerate(facts)}
    sel = {id_of[i] for i in sel1}
    must = set(item["must"])
    target = set(item["target"])
    forbidden = set(item["forbidden"])
    must_hit = len(must & sel)
    tp = len(target & sel)
    precision = tp / len(sel) if sel else 0.0
    recall = tp / len(target) if target else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    must_recall = must_hit / len(must) if must else 1.0
    forbidden_hits = len(forbidden & sel)
    verdict = ("pass" if (must_recall == 1.0 and forbidden_hits == 0
                          and f1 >= F1_GATE) else "fail")
    return {"selected": sorted(sel), "selectedCount": len(sel),
            "totalFacts": len(facts), "selectAll": len(sel) == len(facts),
            "mustRecall": round(must_recall, 3), "forbiddenHits": forbidden_hits,
            "precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(f1, 3), "invalidTokens": bad, "verdict": verdict}


def arm_select_all(item: dict) -> tuple:
    return set(range(1, len(item["facts"]) + 1)), []


def arm_program_rule(item: dict) -> tuple:
    """must + every fact whose entity is visible from the viewpoint. The
    viewpoint rule is applied by the program (the forbidden set is its
    output), never by a model."""
    forbidden = set(item["forbidden"])
    sel = {i + 1 for i, f in enumerate(item["facts"]) if f["factId"] not in forbidden}
    return sel, []


def summarize(rows: list) -> dict:
    n = len(rows)
    return {"items": n,
            "pass": sum(1 for r in rows if r["verdict"] == "pass"),
            "mustRecallMean": round(sum(r["mustRecall"] for r in rows) / n, 3),
            "forbiddenHitsTotal": sum(r["forbiddenHits"] for r in rows),
            "f1Mean": round(sum(r["f1"] for r in rows) / n, 3),
            "selectAllItems": sum(1 for r in rows if r["selectAll"]),
            "invalidTokenItems": sum(1 for r in rows if r["invalidTokens"]),
            "meanSelected": round(sum(r["selectedCount"] for r in rows) / n, 2)}


def run_program_arm(items: list, fn) -> list:
    out = []
    for it in items:
        sel, bad = fn(it)
        out.append({"itemId": it["itemId"], **judge(it, sel, bad)})
    return out


def run_randeng_arm(items: list, variant: str) -> tuple:
    try:
        import pyarrow  # noqa: F401
    except Exception:
        stub = types.ModuleType("pyarrow")
        stub.__version__ = "16.1.0"
        stub.__path__ = []
        sys.modules["pyarrow"] = stub
    tf_stub = types.ModuleType("tensorflow")
    tf_stub.__spec__ = importlib.machinery.ModuleSpec("tensorflow", None)
    tf_stub.__path__ = []
    sys.modules.setdefault("tensorflow", tf_stub)

    import torch
    import transformers
    from transformers.models.t5.modeling_t5 import T5ForConditionalGeneration
    from transformers.models.t5.tokenization_t5 import T5Tokenizer

    tokenizer = T5Tokenizer(vocab_file=str(BASE_MODEL / "spiece.model"), legacy=False)
    model = T5ForConditionalGeneration.from_pretrained(str(BASE_MODEL),
                                                       torch_dtype=torch.float32)
    model.cuda()
    model.eval()
    rows = []
    for it in items:
        prompt = prompt_for(it, variant)
        enc = tokenizer(prompt, return_tensors="pt", truncation=True,
                        max_length=256).to(model.device)
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=MAX_NEW,
                                 num_beams=1, do_sample=False)
        wall = round(time.perf_counter() - t0, 2)
        text = tokenizer.decode(out[0], skip_special_tokens=True)
        sel, bad = parse_ids(text, len(it["facts"]),
                             answer_only=(variant == "b"))
        rows.append({"itemId": it["itemId"], "prompt": prompt, "rawOutput": text,
                     "wallSeconds": wall, "outputTokens": int(out.shape[1]),
                     **judge(it, sel, bad)})
        print(f"[randeng-{variant}] {it['itemId']} {wall}s -> {rows[-1]['verdict']} "
              f"sel={len(sel)}: {text[:40]}")
    env = {"python": sys.version.split()[0], "torch": torch.__version__,
           "transformers": transformers.__version__,
           "device": torch.cuda.get_device_name(0)}
    return rows, env


def main() -> None:
    skip_model = "--skip-model" in sys.argv
    variants = (sys.argv[sys.argv.index("--variants") + 1].split(",")
                if "--variants" in sys.argv else ["a", "b"])
    items = load_items()
    assert len(items) == 16

    arms = {"P0-program-select-all": run_program_arm(items, arm_select_all),
            "P1-program-rule": run_program_arm(items, arm_program_rule)}
    env = None
    if not skip_model:
        for variant in variants:
            rows_v, env = run_randeng_arm(items, variant)
            arms[f"M1{variant}-randeng-zero-shot"] = rows_v

    report = {
        "purpose": "N2 content-selection first comparison round (program baselines + zero-shot)",
        "task": "fact table + viewpoint -> selected fact ids",
        "thresholds": {"f1Gate": F1_GATE,
                       "note": "first-round dev threshold; not a frozen acceptance gate"},
        "decode": {"greedy": True, "maxNewTokens": MAX_NEW, "numBeams": 1,
                   "tokenizerLegacy": False},
        "provenance": {"items": sha_file(ITEMS),
                       "baseModel": {f.name: sha_file(f)[:16]
                                     for f in sorted(BASE_MODEL.iterdir()) if f.is_file()}},
        "environment": env,
        "arms": {name: {"summary": summarize(rows), "rows": rows}
                 for name, rows in arms.items()},
        "disclaimers": [
            "program-defined gold selection; no model output was used as a label",
            "select-all is recorded but never treated as selection ability",
            "dev set only: 16 items, third independent vocabulary",
            "no N2 training yet; M1a/M1b are zero-shot prompt-shape operation points",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    for name, data in report["arms"].items():
        print(f"{name}: {json.dumps(data['summary'], ensure_ascii=False)}")
    print(f"report -> {REPORT}")


if __name__ == "__main__":
    main()
