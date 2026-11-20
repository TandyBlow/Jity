#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Closing delivery verification for c5 group-wording.

Checks: manifest-v2 hashes, both freezes and raw results, checkpoint/organizer
identity, GW-01..GW-19 coverage against the material (no duplicate, no gap),
audit sample sets, and erratum consistency. Writes verify-delivery-v1.json.
Deterministic: no timestamps.
"""
import hashlib
import json
import re
from pathlib import Path

EX = Path(__file__).resolve().parent
ROOT = EX.parents[3]
MATERIAL = ROOT / "artifacts/world-components/organize-wording/sentence-scale-v1.jsonl"
MAT_SHA = "2f537830797986b7678566d0f90ff605749a7ad8f0aadef34cf7c6cd27f43816"
FREEZE1_SHA = "0d8db13f0ca079174504d02fece57514b32672ee53bba3d0e3a9959a9e66f0ed"
FREEZE2_SHA = "34d7be711105a660aa2d4eab29e233f6efd143fe256dd2a6e64f13f74de50f02"
RESULTS1_SHA = "77d7128780c05110a66a994169fea37b6469269a50c33d20f61dbd823bb22aff"
RESULTS2_SHA = "4464b03c02f74f03fc6aff67b242072420e384fa2a6d477bb8fcdc9d25b7bb4a"
CKPT_SHA = "6abd0cdd93f07240526b32b54f2d4800ca33cba5d9cbaf3ce0db907a7d0b4ced"
ORG_SHA = "867dd6dd424f022d736ff5217b25b289827348e7f7db68becf72adfe0d23678f"
RUNNER_SHA = "051f483bbf29be9ba6ed524ba306cd0edc1e188e290e3d1482298841d39a51f4"
MANIFESTS = {"manifest-v1.json", "manifest-v2.json"}
SELF = {"manifest-v1.json", "manifest-v2.json", "verify-delivery-v1.json"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1. manifest-v2: every listed file exists with the listed hash; nothing unlisted
    man = json.loads((EX / "manifest-v2.json").read_text(encoding="utf-8"))
    bad = [k for k, v in man.items() if k not in SELF and (not Path(EX / k).exists() or sha(EX / k) != v)]
    check("manifest-v2 listed files match", not bad, bad)
    listed = set(man) - SELF
    actual = {p.relative_to(EX).as_posix() for p in EX.rglob("*")
              if p.is_file() and p.name not in MANIFESTS and "__pycache__" not in p.parts} - {"verify-delivery-v1.json"}
    check("manifest-v2 has no unlisted file", actual == listed, sorted(actual ^ listed))

    # 2. freeze and raw-output hashes
    check("freeze-v1 hash", sha(EX / "freeze-v1.json") == FREEZE1_SHA, sha(EX / "freeze-v1.json"))
    check("freeze-b2 hash", sha(EX / "freeze-b2-v1.json") == FREEZE2_SHA, sha(EX / "freeze-b2-v1.json"))
    check("run-v1 results hash", sha(EX / "run-v1/results.json") == RESULTS1_SHA, sha(EX / "run-v1/results.json"))
    check("run-b2 results hash", sha(EX / "run-b2-v1/results.json") == RESULTS2_SHA, sha(EX / "run-b2-v1/results.json"))
    st1 = (EX / "freeze-v1.sha256").read_text(encoding="utf-8").split()[0]
    st2 = (EX / "freeze-b2-v1.sha256").read_text(encoding="utf-8").split()[0]
    check("freeze .sha256 files agree", st1 == FREEZE1_SHA and st2 == FREEZE2_SHA, [st1, st2])

    # 3. identity recorded in the freezes
    f1 = json.loads((EX / "freeze-v1.json").read_text(encoding="utf-8"))
    f2 = json.loads((EX / "freeze-b2-v1.json").read_text(encoding="utf-8"))
    for name, f in (("freeze-v1", f1), ("freeze-b2", f2)):
        check(f"{name} checkpoint sha", f["checkpoint"]["model_sha256"] == CKPT_SHA)
        check(f"{name} material sha", f["material"]["sha256"] == MAT_SHA)
        check(f"{name} organizer sha", f["organizer"]["sha256"] == sha(EX / "organizer_v1.py") == ORG_SHA)
    check("runner sha", sha(EX / "run_group_wording_v1.py") == RUNNER_SHA)
    check("freeze-b2 runner sha", f2["runner"]["sha256"] == RUNNER_SHA)

    # 4. prompt counts match the call lists
    for name, f in (("freeze-v1", f1), ("freeze-b2", f2)):
        calls = sum(len(r["A_calls"]) + len(r["B_calls"]) for r in f["rows"])
        check(f"{name} prompt count", len(f["prompts"]) == calls, [len(f["prompts"]), calls])

    # 5. GW coverage against the material: fixed 6 + regression 13, no duplicate, no gap
    raw = MATERIAL.read_bytes().replace(bytes([13, 10]), bytes([10]))
    check("material canonical sha", hashlib.sha256(raw).hexdigest() == MAT_SHA)
    rows = [json.loads(l) for l in raw.decode("utf-8").splitlines()]
    want = {"fixed": set(), "regression": set()}
    for r in rows:
        if r["split"] not in want:
            continue
        for g in r["plan"]["groups"]:
            if len(g["facts"]) >= 2:
                want[r["split"]].add((r["sourceId"], tuple(g["facts"])))
    got = {"fixed": [], "regression": []}
    ids = []
    for f in (f1, f2):
        for s in f["samples"]:
            ids.append(s["sampleId"])
            got["fixed" if s["role"] == "fixed-multi" else "regression"].append(
                (s["sourceId"], tuple(s["groupFacts"])))
    check("GW ids are GW-01..GW-19 in order", ids == [f"GW-{i:02d}" for i in range(1, 20)], ids)
    check("no duplicate GW id", len(ids) == len(set(ids)), len(ids) - len(set(ids)))
    for split in ("fixed", "regression"):
        check(f"{split} group set equals material multi-groups",
              len(got[split]) == len(set(got[split])) and set(got[split]) == want[split],
              {"samples": len(got[split]), "material": len(want[split]),
               "missing": sorted(want[split] - set(got[split])),
               "extra": sorted(set(got[split]) - want[split])})
    check("fixed count 6", len(want["fixed"]) == 6, len(want["fixed"]))
    check("regression count 13", len(want["regression"]) == 13, len(want["regression"]))

    # 6. audit sample sets match the freezes
    a1 = json.loads((EX / "audit-v1.json").read_text(encoding="utf-8"))
    a2 = json.loads((EX / "audit-b2-v1.json").read_text(encoding="utf-8"))
    check("audit-v1 samples", set(a1["samples"]) == {s["sampleId"] for s in f1["samples"]}, sorted(a1["samples"]))
    check("audit-b2 samples", set(a2["samples"]) == {s["sampleId"] for s in f2["samples"]}, sorted(a2["samples"]))
    check("audit determinism flags", a1["determinism_ok"] and a2["determinism_ok"])

    # 7. summary table covers all 19 and split counts agree
    summary = (EX / "summary-19-v1.md").read_text(encoding="utf-8")
    table_ids = re.findall(r"^\| (GW-\d\d) \|", summary, flags=re.M)
    check("summary lists 19 GW ids", table_ids == [f"GW-{i:02d}" for i in range(1, 20)], table_ids)
    check("summary states J 2/19 and S 0/19",
          "1（GW-09 f1）" in summary and "1（GW-07 衣角）" in summary and "0 / 19" in summary)

    # 8. erratum consistency: the wrong quoted sentence only appears in errata lines
    wrong = ("纸灯笼被风扯破一角，排水沟里面积了泥", "排水沟里面积了泥。")
    offenders = []
    for p in sorted(EX.glob("*.md")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            quoted = "S：`" in line or line.startswith("| GW-07 |")
            if quoted and any(w in line for w in wrong) and not any(k in line for k in ("误写", "原记录", "原表")):
                offenders.append(f"{p.name}:{i}: {line.strip()[:60]}")
    check("wrong GW-07 quote only in errata", not offenders, offenders)
    corrected = sum(1 for p in EX.glob("*.md") if "排水沟的里面积了泥" in p.read_text(encoding="utf-8"))
    check("corrected GW-07 text present in review/result docs", corrected >= 2, corrected)
    check("S natural 18/19 in README", "18/19" in (EX / "README.md").read_text(encoding="utf-8"))

    out = {"checks": checks, "passed": all(c["ok"] for c in checks), "count": len(checks),
           "note": "verify-delivery-v1.json is the generated report and is not listed in manifest-v2 (self-reference)."}
    (EX / "verify-delivery-v1.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                                                encoding="utf-8", newline="\n")
    for c in checks:
        print(("PASS " if c["ok"] else "FAIL ") + c["check"], "" if c["ok"] else c["detail"])
    print("all passed" if out["passed"] else "FAILURES PRESENT", out["count"])


if __name__ == "__main__":
    main()
