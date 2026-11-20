# N2 content-selection runner (v2, review round 19 corrections).
#
# Task: given a committed fact table (each fact carries the location it
# happened at) and a COMPLETE viewpoint (type, person, entityId, current
# location, rule text), decide which fact ids go into the narration.
#
# Corrections over the first round:
#  a. The program arm no longer reads answer labels. Two reference arms are
#     reported separately:
#        P1-labels : selection = must + visible, using the `forbidden` LABEL
#                    (kept only as a "given the answer key" reference)
#        P1-rule   : selection derived from viewpoint + fact locations alone
#     An invariance self-test proves the difference: editing labels must not
#     move P1-rule's selection, editing the viewpoint must.
#  b. Prompts carry the complete viewpoint (person, id, location) and every
#     fact line is tagged with its location, so a model CAN apply the rule.
#  c. The judge is strict: anything other than ids/separators (plus an
#     optional 「编号：」 prefix) invalidates the answer — "ids plus prose" no
#     longer passes.
#
# Arms: P0 select-all, P1-labels (reference), P1-rule (program), M1a/M1b
# Randeng zero-shot (instruction after data / answer slot).
#
# Judge: mustRecall == 1, forbiddenHits == 0, F1 >= 0.6 (first-round dev
# threshold, not a frozen gate), and no invalid content.
#
# Usage: python experiments/world-components/n2_selection/run_n2.py [--skip-model]
# Output: artifacts/world-components/n2-selection-r2.json

import copy
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
REPORT = REPO / "artifacts" / "world-components" / "n2-selection-r2.json"

F1_GATE = 0.6
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
    where = "全局" if f.get("at") is None else f["at"]
    k = f["kind"]
    if k == "moved":
        body = f"位置：{f['name']} 从{f['from']}到{f['to']}"
    elif k == "task_achieved":
        body = f"任务达成：{f['name']}「{f['goal']}」"
    elif k == "personality_changed":
        body = f"个性：{f['name']}{f['text']}"
    elif k == "sanity_changed":
        d = "上升" if f["to"] > f["from"] else "下降" if f["to"] < f["from"] else "不变"
        body = f"理智：{f['name']} {f['from']}→{f['to']}（{d}）"
    elif k == "appearance_changed":
        body = f"外貌：{f['name']} {f['text']}"
    elif k == "positioned_at":
        body = f"现状：{f['name']} 已在{f['at']}"
    elif k == "time":
        body = f"时间推进：约{f['amount']}分钟"
    elif k == "no_change":
        body = f"无变化：{f.get('scope') or f.get('at')}"
    else:
        raise ValueError(f"unknown fact kind {k}")
    return f"{i}. [{where}] {body}"


def prompt_for(item: dict, variant: str = "a") -> str:
    v = item["viewpoint"]
    who = (f"{v['name']}（{v['entityId']}）" if v.get("entityId")
           else "全知叙述者")
    where = v.get("at") or "全局"
    lines = [fact_line(i + 1, f) for i, f in enumerate(item["facts"])]
    body = ("叙事选材任务。\n"
            f"视角人物：{who}，当前在{where}。\n"
            f"视角规则：{v['rule']}。\n"
            "事实（方括号内是事实发生的地点）：\n" + "\n".join(lines) + "\n")
    if variant == "a":
        return (body + "任务：选出必须写进正文的事实编号，视角看不到的不要选。\n"
                + "只输出编号，用逗号分隔，不要写其他文字。")
    if variant == "b":
        return ("选材。只输出要写进正文的事实编号，不要写其他文字。\n" + body + "编号：")
    raise ValueError(variant)


# STRICT format: optional 「编号：」 prefix, then digits separated by commas,
# optionally ending with one full stop. Anything else is invalid content.
ID_LIST = re.compile(r"^[\s　]*(?:编号[:：][\s　]*)?\d+(?:[\s　]*[,，、;；][\s　]*\d+)*[。.]?[\s　]*$")


def parse_ids(text: str, n_facts: int, answer_only: bool = False) -> tuple:
    """-> (selected ids, invalid reason or None). Strict by design."""
    raw = text
    if answer_only and "编号" in text:
        text = text.rsplit("编号", 1)[1].lstrip(":：")
    if not text.strip():
        return set(), "empty"
    if not ID_LIST.match(text):
        return set(), f"non-id-content: {raw.strip()[:40]!r}"
    sel = {int(x) for x in re.findall(r"\d+", text)}
    bad = sorted(x for x in sel if not (1 <= x <= n_facts))
    if bad:
        return set(), f"out-of-range ids {bad}"
    return sel, None


def judge(item: dict, sel1: set, invalid) -> dict:
    id_of = {i + 1: f["factId"] for i, f in enumerate(item["facts"])}
    sel = {id_of[i] for i in sel1}
    must = set(item["must"])
    target = set(item["target"])
    forbidden = set(item["forbidden"])
    precision = len(target & sel) / len(sel) if sel else 0.0
    recall = len(target & sel) / len(target) if target else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    must_recall = len(must & sel) / len(must) if must else 1.0
    forbidden_hits = len(forbidden & sel)
    verdict = ("pass" if (invalid is None and must_recall == 1.0
                          and forbidden_hits == 0 and f1 >= F1_GATE) else "fail")
    return {"selected": sorted(sel), "selectedCount": len(sel),
            "totalFacts": len(item["facts"]),
            "selectAll": len(sel) == len(item["facts"]),
            "mustRecall": round(must_recall, 3), "forbiddenHits": forbidden_hits,
            "precision": round(precision, 3), "recall": round(recall, 3),
            "f1": round(f1, 3), "invalid": invalid, "verdict": verdict}


# ---- reference / program arms -------------------------------------------
def visible_from_viewpoint(vp: dict, fact: dict) -> bool:
    """Independent implementation of the visibility rule (v2): reads ONLY the
    viewpoint fields and the fact's own entityId/location — never labels."""
    if vp["type"] == "omniscient":
        return True
    if fact["kind"] == "time":
        return True
    if fact.get("entityId") and fact["entityId"] == vp.get("entityId"):
        return True
    return fact.get("at") == vp.get("at") and fact["kind"] != "time"


def arm_select_all(item: dict) -> tuple:
    return set(range(1, len(item["facts"]) + 1)), None


def arm_rule(item: dict) -> tuple:
    vp = item["viewpoint"]
    sel = {i + 1 for i, f in enumerate(item["facts"])
           if visible_from_viewpoint(vp, f)}
    return sel, None


def arm_labels(item: dict) -> tuple:
    """REFERENCE arm: uses the answer key (must + forbidden). Kept only to
    show what the label set implies; it proves nothing about the viewpoint
    rule being implemented."""
    forbidden = set(item["forbidden"])
    sel = {i + 1 for i, f in enumerate(item["facts"])
           if f["factId"] not in forbidden}
    return sel, None


def summarize(rows: list) -> dict:
    n = len(rows)
    return {"items": n,
            "pass": sum(1 for r in rows if r["verdict"] == "pass"),
            "mustRecallMean": round(sum(r["mustRecall"] for r in rows) / n, 3),
            "forbiddenHitsTotal": sum(r["forbiddenHits"] for r in rows),
            "f1Mean": round(sum(r["f1"] for r in rows) / n, 3),
            "selectAllItems": sum(1 for r in rows if r["selectAll"]),
            "invalidItems": sum(1 for r in rows if r["invalid"]),
            "meanSelected": round(sum(r["selectedCount"] for r in rows) / n, 2)}


def run_program_arm(items: list, fn) -> list:
    return [{"itemId": it["itemId"], **judge(it, *fn(it))} for it in items]


def invariance_selftest(items: list) -> dict:
    """The reviewer's probes: labels must not move the rule arm; viewpoint
    must. Also pins the strict judge."""
    void = []
    labels_changed = 0
    for it in items:
        tampered = copy.deepcopy(it)
        tampered["forbidden"] = []          # labels only
        if arm_rule(tampered) != arm_rule(it):
            labels_changed += 1
    if labels_changed:
        void.append(f"rule arm moved when only labels changed ({labels_changed} items)")

    vp_changed = 0
    for it in items:
        if it["viewpoint"]["type"] == "omniscient":
            continue                        # omnivisible: location change is a no-op
        tampered = copy.deepcopy(it)
        others = [f["at"] for f in it["facts"]
                  if f.get("at") and f["at"] != it["viewpoint"]["at"]]
        if not others:
            continue
        tampered["viewpoint"]["at"] = others[0]
        if arm_rule(tampered) != arm_rule(it):
            vp_changed += 1
    if vp_changed == 0:
        void.append("rule arm did not move when the viewpoint location changed")

    # the labels arm MUST move on the label probe (documents that it reads them)
    label_arm_moved = 0
    for it in items:
        tampered = copy.deepcopy(it)
        tampered["forbidden"] = []
        if arm_labels(tampered) != arm_labels(it):
            label_arm_moved += 1

    # strict judge: ids plus prose must not pass
    probe_item = items[0]
    sel, invalid = parse_ids("1,2 我觉得就这样", len(probe_item["facts"]))
    if invalid is None:
        void.append("strict judge accepted ids plus prose")
    sel2, invalid2 = parse_ids("1,2", len(probe_item["facts"]))
    if invalid2 is not None:
        void.append(f"strict judge rejected a clean id list: {invalid2}")
    if void:
        print("REPORT VOID — invariance self-test failed:")
        for x in void:
            print(" ", x)
        sys.exit(2)
    return {"ruleArmItemsMovedByLabelChange": labels_changed,
            "ruleArmItemsMovedByViewpointChange": vp_changed,
            "labelArmItemsMovedByLabelChange": label_arm_moved,
            "judgeRejectsIdsPlusProse": True,
            "judgeAcceptsCleanIds": True}


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
                        max_length=320).to(model.device)
        t0 = time.perf_counter()
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=MAX_NEW,
                                 num_beams=1, do_sample=False)
        wall = round(time.perf_counter() - t0, 2)
        text = tokenizer.decode(out[0], skip_special_tokens=True)
        sel, invalid = parse_ids(text, len(it["facts"]), answer_only=(variant == "b"))
        rows.append({"itemId": it["itemId"], "prompt": prompt, "rawOutput": text,
                     "wallSeconds": wall, "outputTokens": int(out.shape[1]),
                     **judge(it, sel, invalid)})
        print(f"[randeng-{variant}] {it['itemId']} {wall}s -> {rows[-1]['verdict']} "
              f"sel={len(sel)} invalid={rows[-1]['invalid']}")
    env = {"python": sys.version.split()[0], "torch": torch.__version__,
           "transformers": transformers.__version__,
           "device": torch.cuda.get_device_name(0)}
    return rows, env


def main() -> None:
    skip_model = "--skip-model" in sys.argv
    variants = (sys.argv[sys.argv.index("--variants") + 1].split(",")
                if "--variants" in sys.argv else ["a", "b"])
    items = load_items()
    assert len(items) == 16 and all(r.get("batch") == "v2" for r in items)

    selftest = invariance_selftest(items)
    print(f"self-test PASS: {selftest}")

    arms = {
        "P0-program-select-all": run_program_arm(items, arm_select_all),
        "P1-labels-reference": run_program_arm(items, arm_labels),
        "P1-rule-program": run_program_arm(items, arm_rule),
    }
    env = None
    if not skip_model:
        for variant in variants:
            rows_v, env = run_randeng_arm(items, variant)
            arms[f"M1{variant}-randeng-zero-shot"] = rows_v

    report = {
        "purpose": "N2 content-selection round 2 (corrected design: labels not read by arms, "
                   "complete viewpoint, strict judge)",
        "task": "fact table (with per-fact locations) + complete viewpoint -> selected fact ids",
        "thresholds": {"f1Gate": F1_GATE,
                       "note": "first-round dev threshold; not a frozen acceptance gate"},
        "decode": {"greedy": True, "maxNewTokens": MAX_NEW, "numBeams": 1,
                   "tokenizerLegacy": False},
        "selfTest": selftest,
        "provenance": {"items": sha_file(ITEMS),
                       "itemsBatch": "v2",
                       "baseModel": {f.name: sha_file(f)[:16]
                                     for f in sorted(BASE_MODEL.iterdir()) if f.is_file()}},
        "environment": env,
        "arms": {name: {"summary": summarize(rows), "rows": rows}
                 for name, rows in arms.items()},
        "disclaimers": [
            "P1-labels reads the answer key and is a reference only; P1-rule reads viewpoint+facts",
            "program-defined gold selection; no model output was used as a label",
            "select-all is recorded but never treated as selection ability",
            "dev set only: 16 items, third independent vocabulary, batch v2",
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
