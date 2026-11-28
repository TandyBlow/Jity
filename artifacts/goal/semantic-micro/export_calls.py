#!/usr/bin/env python3
"""Export per-task datasets from frozen acceptance evidence.

Input: WorldTurnRecord.product.semanticPrompts (full engine prompts) and
semanticCalls (task/key/source/raw/ms). Output JSONL under --out (default
experiments/semantic-micro/export).

The join is best effort and reports unmatched prompts: action/targets/narration
prompts pair with their attempt/result rows in order; settlement stages pair by
prompt signature with the stage's model call. Verifier prompts are parsed into
(task goal, fact) cases and matched to any verdict JSON in the turn.

Usage: python artifacts/goal/semantic-micro/export_calls.py EVIDENCE [--out DIR]
"""
import argparse
import json
import os
import re
from collections import Counter, defaultdict

SIGNATURES = [
    ("action", "角色行动判断器"),
    ("targets", "牵连判断器"),
    ("reaction", "反应生成器"),
    ("verifier", "任务条件核验器"),
    ("tasks", "任务判定器"),
    ("subtasks", "新增小任务判断器"),
    ("personality", "人物个性变化判断器"),
    ("sanity", "人物理智重算器"),
    ("results", "共同结算器"),
    ("position", "位置结算器"),
    ("appearance", "外貌结算器"),
    ("narration", "中文小说作者"),
]

FACT_LINE = re.compile(r"^f\d+ \[([^\]]*)\] (.*)$")
VERIFIER_ROW = re.compile(r"^- (.+?)（([^）]+)）任务 (\S+)：(.+)\n  依据：(.+)$", re.M)
TASK_ROW = re.compile(r"^(.+?)（id=([\w-]+)）(.*)$")
TASK_ITEM = re.compile(r"(t\d+)：(.+?)（(待办|已完成)）(?=；|$)")
SUBTASK_ITEM = re.compile(r"(t\d+)：([^；]+)(?:；|$)")


def classify(prompt):
    for name, marker in SIGNATURES:
        if marker in prompt:
            return name
    return "other"


def parse_facts(prompt):
    facts = []
    for line in prompt.splitlines():
        match = FACT_LINE.match(line.strip())
        if match:
            tag = match.group(1).split()
            facts.append({"id": line.strip().split(" ", 1)[0], "memberId": tag[0] if tag else "", "text": match.group(2)})
    return facts


def parse_verifier(prompt):
    return [
        {"ownerName": m.group(1), "characterId": m.group(2), "taskId": m.group(3),
         "goal": m.group(4).strip(), "factText": m.group(5).strip()}
        for m in VERIFIER_ROW.finditer(prompt)
    ]


def parse_task_rows(prompt):
    rows = []
    for line in prompt.splitlines():
        if not line.startswith("- "):
            continue
        head = TASK_ROW.match(line)
        if not head:
            continue
        tail = head.group(3)
        items = list(TASK_ITEM.finditer(tail))
        for item in items:
            rows.append({"ownerId": head.group(2), "taskKey": item.group(1), "goal": item.group(2), "status": item.group(3)})
    return rows


def parse_subtask_rows(prompt):
    rows = []
    for line in prompt.splitlines():
        if not line.startswith("- "):
            continue
        head = TASK_ROW.match(line)
        if not head or "待办任务" not in head.group(3):
            continue
        tail = head.group(3).split("待办任务", 1)[1].lstrip("：")
        for item in SUBTASK_ITEM.finditer(tail):
            rows.append({"ownerId": head.group(2), "taskKey": item.group(1), "goal": item.group(2)})
    return rows


def json_objects(raw):
    """Parse every JSON object an engine call may have produced.

    Repairs are joined with a '---' separator and some answers contain prose
    around the object, so a single first-brace/last-brace parse is not enough.
    """
    if not isinstance(raw, str):
        return []
    out = []
    for segment in raw.split("\n---\n"):
        text = segment.strip()
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            continue
        for candidate in (text[start:end + 1],):
            try:
                value = json.loads(candidate)
                if isinstance(value, dict):
                    out.append(value)
            except json.JSONDecodeError:
                for line in text.splitlines():
                    line = line.strip()
                    if not (line.startswith("{") and line.endswith("}")):
                        continue
                    try:
                        value = json.loads(line)
                        if isinstance(value, dict):
                            out.append(value)
                    except json.JSONDecodeError:
                        continue
    return out


def answer_from_call(call):
    if not call:
        return None
    objects = json_objects(call.get("raw"))
    return objects[0] if objects else None


def collect_answers(data):
    """All JSON objects produced in a turn, keyed by their shape."""
    out = {"tasks": [], "subtasks": [], "verifier": [], "raw_all": []}
    for turn in data.get("turns") or []:
        product = turn.get("product") or {}
        raws = [c.get("raw") for c in product.get("semanticCalls") or []
                if c.get("source") == "model" and c.get("raw")]
        for call in (turn.get("submission") or {}).get("calls") or []:
            if call.get("raw"):
                raws.append(call["raw"])
        for raw in raws:
            out["raw_all"].append(raw)
            for value in json_objects(raw):
                keys = set(value)
                if "judgments" in keys:
                    out["verifier"].extend(value["judgments"])
                elif "subtasks" in keys and ("achieved" in keys or "unchanged" in keys):
                    out["tasks"].append(value)
                elif "subtasks" in keys:
                    out["subtasks"].append(value)
    return out


def export(path, out_dir):
    data = json.load(open(path, encoding="utf-8"))
    all_answers = collect_answers(data)
    verdicts_by_key = defaultdict(list)
    for row in all_answers["verifier"]:
        verdicts_by_key[(row.get("characterId"), row.get("taskId"))].append(row)
    stem = os.path.splitext(os.path.basename(path))[0]
    prompts_path = os.path.join(out_dir, f"{stem}.prompts.jsonl")
    pairs_path = os.path.join(out_dir, f"{stem}.pairs.jsonl")
    tasks_path = os.path.join(out_dir, f"{stem}.tasks.jsonl")
    verifier_path = os.path.join(out_dir, f"{stem}.verifier.jsonl")
    subtasks_path = os.path.join(out_dir, f"{stem}.subtasks.jsonl")
    stats = Counter()
    count_mismatch = Counter()
    with open(prompts_path, "w", encoding="utf-8") as prompts_f, \
            open(pairs_path, "w", encoding="utf-8") as pairs_f, \
            open(tasks_path, "w", encoding="utf-8") as tasks_f, \
            open(verifier_path, "w", encoding="utf-8") as verifier_f, \
            open(subtasks_path, "w", encoding="utf-8") as subtasks_f:
        for turn in data.get("turns") or []:
            product = turn.get("product") or {}
            answers = collect_answers({"turns": [turn]})
            calls_by_kind = defaultdict(list)
            for call in product.get("semanticCalls") or []:
                if call.get("source") != "model":
                    continue
                task = call["task"]
                if task in ("action", "targets", "reaction"):
                    if call.get("attempt"):
                        calls_by_kind[task].append(call)
                    continue
                if task == "updates":
                    stage = (call.get("key") or "").split("#")[-1]
                    calls_by_kind[stage].append(call)
                else:
                    calls_by_kind[task].append(call)
            prompts = product.get("semanticPrompts") or []
            groups = defaultdict(list)
            for item in prompts:
                kind = classify(item.get("prompt") or "")
                groups[kind].append(item.get("prompt") or "")
                stats[kind] += 1
                prompts_f.write(json.dumps({
                    "file": path, "turn": turn.get("turn"), "kind": kind,
                    "prompt": item.get("prompt") or "",
                }, ensure_ascii=False) + "\n")
            for kind, group in groups.items():
                calls = calls_by_kind.get(kind) or []
                if len(group) != len(calls):
                    count_mismatch[kind] += abs(len(group) - len(calls))
                for index, prompt in enumerate(group):
                    call = calls[index] if index < len(calls) else None
                    pairs_f.write(json.dumps({
                        "file": path, "turn": turn.get("turn"), "kind": kind, "prompt": prompt,
                        "call": None if call is None else {
                            "task": call["task"], "key": call.get("key"), "raw": call.get("raw"),
                            "ms": call.get("ms"), "issues": call.get("issues"),
                            "attempt": call.get("attempt"),
                        },
                    }, ensure_ascii=False) + "\n")
            for kind in ("verifier", "tasks", "subtasks"):
                prompts_of_kind = groups.get(kind) or []
                stage_calls = calls_by_kind.get(kind) or []
                for index, prompt_text in enumerate(prompts_of_kind):
                    call = stage_calls[index] if index < len(stage_calls) else None
                    if kind == "verifier":
                        cases = parse_verifier(prompt_text)
                        for case in cases:
                            candidates = verdicts_by_key.get((case["characterId"], case["taskId"])) or []
                            labels = {row.get("satisfied") for row in candidates}
                            match = candidates[0] if len(labels) == 1 else None
                            if len(labels) > 1:
                                match = {"ambiguous": sorted(labels)}
                            verifier_f.write(json.dumps({
                                "file": path, "turn": turn.get("turn"), "prompt": prompt_text,
                                "case": case, "verdict": match,
                                "status": "labeled" if match else "unlabeled",
                            }, ensure_ascii=False) + "\n")
                        stats["verifier_cases"] += len(cases)
                        stats["verifier_labeled"] += sum(
                            1 for c in cases
                            if (c["characterId"], c["taskId"]) in verdicts_by_key)
                    elif kind == "tasks":
                        rows = parse_task_rows(prompt_text)
                        answer = answer_from_call(call) or (answers["tasks"][0] if answers["tasks"] else None)
                        tasks_f.write(json.dumps({
                            "file": path, "turn": turn.get("turn"), "prompt": prompt_text,
                            "facts": parse_facts(prompt_text), "rows": rows, "answer": answer,
                            "call": None if call is None else {"ms": call.get("ms"), "raw": call.get("raw")},
                        }, ensure_ascii=False) + "\n")
                        stats["tasks_cases"] += 1
                        stats["tasks_rows"] += len(rows)
                    else:
                        rows = parse_subtask_rows(prompt_text)
                        answer = answer_from_call(call) or (answers["subtasks"][0] if answers["subtasks"] else None)
                        subtasks_f.write(json.dumps({
                            "file": path, "turn": turn.get("turn"), "prompt": prompt_text,
                            "facts": parse_facts(prompt_text), "rows": rows, "answer": answer,
                            "call": None if call is None else {"ms": call.get("ms"), "raw": call.get("raw")},
                        }, ensure_ascii=False) + "\n")
                        stats["subtasks_cases"] += 1
    return stats, count_mismatch, {"prompts": prompts_path, "pairs": pairs_path,
                                   "tasks": tasks_path, "verifier": verifier_path,
                                   "subtasks": subtasks_path}


def selftest():
    import tempfile
    sample = "\n".join([
        "当前世界时间：2009-10-17T15:21:00",
        "本组结算结果（任务达成必须引用其中的编号）：",
        "f1 [lu 路明非] 路明非找到护目镜（达到目的）",
        "你是中文跑团游戏的任务条件核验器。只输出 JSON，不要解释。",
        "任务：",
        "- 路明非（lu）任务 task_lu_kit：找到护目镜",
        "  依据：路明非找到护目镜（达到目的）",
        "输出 {\"judgments\":[]}",
    ])
    assert classify(sample) == "verifier"
    assert classify("你是中文跑团游戏的任务判定器。只输出 JSON，不要解释。") == "tasks"
    cases = parse_verifier(sample)
    assert cases == [{"ownerName": "路明非", "characterId": "lu", "taskId": "task_lu_kit",
                      "goal": "找到护目镜", "factText": "路明非找到护目镜（达到目的）"}], cases
    tasks_sample = "\n".join([
        "f1 [lu 路明非] 路明非找到护目镜（达到目的）",
        "- 路明非（id=lu）位置=lane；外貌=普通；个性=谨慎：t1：找到护目镜（待办）；t2：完成比赛（已完成）",
    ])
    rows = parse_task_rows(tasks_sample)
    assert rows == [
        {"ownerId": "lu", "taskKey": "t1", "goal": "找到护目镜", "status": "待办"},
        {"ownerId": "lu", "taskKey": "t2", "goal": "完成比赛", "status": "已完成"},
    ], rows
    assert parse_facts(tasks_sample)[0]["memberId"] == "lu"
    with tempfile.TemporaryDirectory() as tmp:
        evidence = {
            "status": "COMPLETED",
            "turns": [{
                "turn": 1,
                "product": {
                    "semanticPrompts": [{"at": 1, "prompt": sample}],
                    "semanticCalls": [
                        {"task": "updates", "key": "p#tasks", "source": "model", "raw": "{\"judgments\":[{\"characterId\":\"lu\",\"taskId\":\"task_lu_kit\",\"satisfied\":\"yes\",\"reason\":\"ok\"}]}", "ms": 5},
                    ],
                },
                "submission": {"calls": [{"raw": "{\"judgments\":[{\"characterId\":\"lu\",\"taskId\":\"task_lu_kit\",\"satisfied\":\"yes\",\"reason\":\"ok\"}]}"}]},
            }],
        }
        path = os.path.join(tmp, "evidence.json")
        json.dump(evidence, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        stats, mismatch, files = export(path, tmp)
        assert stats["verifier_cases"] == 1 and stats["verifier_labeled"] == 1, stats
        assert os.path.exists(files["pairs"])
    print("selftest ok")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", nargs="*")
    parser.add_argument("--out", default="experiments/semantic-micro/export")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
        return
    os.makedirs(args.out, exist_ok=True)
    for path in args.evidence:
        stats, count_mismatch, files = export(path, args.out)
        print(f"== {path}")
        print("   ", dict(sorted(stats.items())))
        if count_mismatch:
            print("    prompt/call count mismatch:", dict(count_mismatch))
        print("    wrote", files)


if __name__ == "__main__":
    main()
