#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build freeze-v1.json for the group-wording split-vs-joint comparison.

Reads the registered material and the recorded 77M/784M runs, selects 9 rows /
10 samples, and freezes every prompt, the sample list and the recorded control
texts. Deterministic; no model calls.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
EX = ROOT / "experiments/world-components/parallel/group_wording"
MATERIAL = ROOT / "artifacts/world-components/organize-wording/sentence-scale-v1.jsonl"
MAT_SHA = "2f537830797986b7678566d0f90ff605749a7ad8f0aadef34cf7c6cd27f43816"
RUN77 = ROOT / "artifacts/world-components/organize-wording/sentence-scale-run-v1/results.json"
RUN784 = ROOT / "artifacts/world-components/organize-wording/sentence-base-784m-run-v1/results.json"

ROW_IDS = ["n4n-109", "n4n-64", "n4n-65", "n4n-74", "n4n-75", "n4n-87", "t24", "v20", "v07"]
SAMPLES = [
    ("GW-01", "n4n-109", ["f1", "f2"], "fixed-multi"),
    ("GW-02", "n4n-64", ["f0", "f1"], "fixed-multi"),
    ("GW-03", "n4n-65", ["f0", "f1"], "fixed-multi"),
    ("GW-04", "n4n-74", ["f0", "f1"], "fixed-multi"),
    ("GW-05", "n4n-75", ["f0", "f1"], "fixed-multi"),
    ("GW-06", "n4n-87", ["f0", "f1"], "fixed-multi"),
    ("GW-07", "t24", ["f0", "f1"], "regression-multi"),
    ("GW-08", "t24", ["f2", "f3"], "regression-multi"),
    ("GW-09", "v20", ["f0", "f1", "f2"], "regression-multi"),
    ("GW-10", "v07", ["f0", "f1"], "regression-multi"),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fact_line(f):
    k = f["kind"]
    if k == "moved":
        return f"{f['factId']}｜移动｜{f['name']}｜{f['from']}→{f['to']}｜方向={f.get('direction','平')}"
    if k == "outcome":
        return f"{f['factId']}｜结果｜{f['name']}｜{f['text']}"
    if k == "appearance_changed":
        return f"{f['factId']}｜外观｜{f['name']}｜{f['text']}"
    if k == "sanity_changed":
        return f"{f['factId']}｜理智｜{f['name']}｜{f['from']}→{f['to']}"
    if k == "no_change":
        return f"{f['factId']}｜无变化"
    if k == "time":
        return f"{f['factId']}｜时间"
    if k == "position_relative":
        return f"{f['factId']}｜位置｜{f['name']}｜{f['text']}"
    return f"{f['factId']}｜{k}｜{f.get('name','')}｜{f.get('text','')}"


def prompt_call(r, call, idx, total):
    c = r["context"]
    fm = {f["factId"]: f for f in r["facts"]}
    lines = ["叙事任务。",
             f"地点={c.get('place','')}",
             f"地点可见={c.get('visible','')}",
             f"场景={c.get('scene','')}",
             f"视角={c.get('viewpoint','')}",
             f"本组={idx}/{total}",
             "事实（只列本组，按顺序）："]
    lines += [fact_line(fm[fid]) for fid in call["factIds"]]
    lines += ["要求：只写本组；组内可联合多条事实；组间边界由程序负责；不新增人物、物品、地点、动作、关系；不写代词、数字、字段名；需要称呼时用姓名。",
              "正文："]
    return "\n".join(lines) + "\n"


def main():
    raw = MATERIAL.read_bytes()
    canon = raw.replace(bytes([13, 10]), bytes([10]))
    assert hashlib.sha256(canon).hexdigest() == MAT_SHA, hashlib.sha256(canon).hexdigest()
    rows = {json.loads(l)["sourceId"]: json.loads(l) for l in canon.decode("utf-8").splitlines()}
    r77 = json.loads(RUN77.read_text(encoding="utf-8"))
    r784 = json.loads(RUN784.read_text(encoding="utf-8"))

    frozen_rows = []
    prompts = {}
    for sid in ROW_IDS:
        r = rows[sid]
        split = r["split"]
        fa = []
        for i, c in enumerate(r["A"]["calls"]):
            pid = f"A:{c['callId']}"
            prompts[pid] = prompt_call(r, c, i + 1, len(r["A"]["calls"]))
            fa.append({"callId": c["callId"], "factIds": c["factIds"], "idx": i + 1, "total": len(r["A"]["calls"])})
        fb = []
        for i, c in enumerate(r["B"]["calls"]):
            pid = f"B:{c['callId']}"
            prompts[pid] = prompt_call(r, c, i + 1, len(r["B"]["calls"]))
            fb.append({"callId": c["callId"], "factIds": c["factIds"], "idx": i + 1, "total": len(r["B"]["calls"])})
        frozen_rows.append({
            "sourceId": sid, "split": split, "sceneGroup": r["sceneGroup"],
            "context": r["context"], "facts": r["facts"], "plan": r["plan"],
            "A_calls": fa, "B_calls": fb,
            "recorded_784_assembled": r784[split][sid]["assembled"],
            "recorded_B77_assembled": r77["arms"]["B-large"][split][sid]["assembled"],
            "recorded_A77_assembled": r77["arms"]["A-large"][split][sid]["assembled"],
        })

    samples = [{"sampleId": s[0], "sourceId": s[1], "groupFacts": s[2], "role": s[3]} for s in SAMPLES]
    prompt_bytes = json.dumps(prompts, ensure_ascii=False, sort_keys=True).encode("utf-8")
    freeze = {
        "protocol": "group-wording-v1",
        "created": "2026-11-08",
        "question": "Per-fact calls + deterministic organizer (arm S) vs joint group call (arm J), same checkpoint, no training.",
        "material": {"path": str(MATERIAL.relative_to(ROOT)), "sha256": MAT_SHA,
                     "local_raw_sha256": hashlib.sha256(raw).hexdigest(),
                     "note": "checkout is CRLF; canonical hash is over LF-normalized bytes, same as HPC copy and the recorded freeze"},
        "checkpoint": {
            "name": "sentence-base-784m ckpt-final",
            "remote_path": "~/sentence784_run/out/ckpt-final",
            "model_sha256": "6abd0cdd93f07240526b32b54f2d4800ca33cba5d9cbaf3ce0db907a7d0b4ced",
            "spiece_sha256": "c65feffa65ff0378759778193852083d23349cb1b40c906e9463a12f8076ff32",
            "why": "the only surviving checkpoint behind either recorded 2/19 result; B77 weights were never saved",
        },
        "decoding": {"max_input": 512, "max_new": 128, "num_beams": 1, "do_sample": False,
                     "batch": 6, "stop_on_eos": True},
        "organizer": {"file": "organizer_v1.py", "sha256": sha(EX / "organizer_v1.py"),
                      "version": "v1: same-entity continuation merge, group join with '。', edge target gets '随后，'"},
        "rows": frozen_rows,
        "samples": samples,
        "prompts": prompts,
        "prompts_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "determinism_check": "arm J must reproduce recorded_784_assembled byte-for-byte on all 9 rows",
    }
    out = EX / "freeze-v1.json"
    out.write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    (EX / "freeze-v1.sha256").write_text(sha(out) + "  freeze-v1.json\n", encoding="utf-8", newline="\n")
    print("wrote", out, sha(out))
    print("prompts", len(prompts), "prompts_sha256", freeze["prompts_sha256"])
    print("samples", len(samples), "rows", len(frozen_rows))


if __name__ == "__main__":
    main()
