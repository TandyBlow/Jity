# Contract probes: run the frozen v2 N5 gate over hand-written candidate
# texts for two contract conflicts that the 19-case composition exposed.
#
# This does NOT re-run the composition and does NOT touch the frozen
# 19-case archive. It reads that archive (facts + plan per case), feeds the
# extra texts through the SAME judge (eval_n4_v2.judge_row), and archives
# the verdicts. All probes are offline CPU, no model call.
#
#   P1 task title, quoted        expectation: pass  (the archived text)
#   P2 task title, paraphrased   expectation: G1 fail (variant without the
#                                goal quote)  -> N4.0's "不写任务标题" and the
#                                v2 frame cannot both be satisfied
#   P3 time, vague               expectation: G3 fail (the archived text)
#   P4 time, exact value         expectation: pass -> only the exact value
#                                satisfies G3, contradicting N4.0's vague
#                                time line and its "不写具体时长" rule
#   S1 outcome kind (SYNTHETIC)  expectation: the judge has no frame for
#                                `outcome` and raises ValueError -> the
#                                "switch task facts to resultText" option for
#                                D1 is not evaluable by the current gate
#
# S1 constructs its row from the archived normal-move-task facts (the task
# fact rewritten to `outcome` + resultText) and is labelled synthetic: it is
# not a fact set produced by N1.
#
# Usage: python -X utf8 contract_probes.py [--run out/composition-run.json]
#                                           [--out out/contract-probes.json]

import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent
for p in (str(WC), str(WC / "n4_corpus_v2")):
    if p not in sys.path:
        sys.path.insert(0, p)

from eval_n4_v2 import judge_row  # noqa: E402

DEFAULT_RUN = HERE / "out" / "composition-run.json"
DEFAULT_OUT = HERE / "out" / "contract-probes.json"

# caseId -> [(probeId, text, why)]
PROBES = {
    "normal-move-task": [
        ("task-title-quoted",
         "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。",
         "archived accepted text: the task goal is quoted verbatim"),
        ("task-title-paraphrased",
         "管线甲从管线镇来到了钟楼。他把铜铃挂回了钟楼。",
         "same facts, no task title: the goal text is paraphrased instead"),
    ],
    "contract-time-conflict": [
        ("time-vague",
         "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。"
         "过了一会儿。",
         "archived text: N4.0-compliant vague time, no duration"),
        ("time-exact",
         "管线甲从管线镇来到了钟楼。管线甲完成了任务「把铜铃挂回钟楼」。"
         "前后大约八分钟过去了。",
         "exact planned duration: satisfies G3 but contradicts N4.0 and its "
         "'不写具体时长' rule"),
    ],
}


# Synthetic rows: built from an archived case's facts, then transformed.
# They are labelled `synthetic: true` in the archive so they can never be
# mistaken for N1 output.
SYNTHETIC = [
    {
        "probeId": "outcome-kind-unsupported",
        "caseId": "normal-move-task",
        "why": "D1 option A: express the completed task as `outcome` + "
               "resultText (what N2/N4.0 already carry) instead of the task "
               "title. The frozen v2 judge has no pattern for `outcome`.",
        "transform": "task_achieved -> outcome(+resultText)",
        "text": "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。",
    },
]


def judge_synthetic(probe, base):
    """Build the synthetic row and judge it; a judge ValueError is recorded
    as a capability gap, not as a verdict."""
    facts = []
    for f in base["facts"]:
        g = dict(f)
        if g.get("kind") == "task_achieved":
            g["kind"] = "outcome"
            g["resultText"] = "把铜铃挂回了钟楼"
        facts.append(g)
    row = {"rowId": f"comp:{probe['caseId']}",
           "facts": facts, "mustExpress": list(base["mustExpress"]),
           "plan": base["plan"]}
    try:
        verdict = judge_row(row, probe["text"], "eos")
        return {"pass": verdict["pass"], "gates": verdict["gates"],
                "problems": verdict["align"]["problems"]}
    except ValueError as exc:
        return {"pass": None, "judgeError": str(exc),
                "note": "the gate cannot evaluate this fact kind at all, so "
                        "no verdict exists"}


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", default=str(DEFAULT_RUN))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    run = json.loads(pathlib.Path(args.run).read_text(encoding="utf-8"))
    by_id = {c["caseId"]: c for c in run["cases"]}

    probes = []
    for cid, items in PROBES.items():
        case = by_id[cid]
        selected_ids = case["selectedFactIds"]
        # The archive stores the full N1 fact set under stages.n1.facts and
        # the N3 plan under stages.organization.response; the judge needs
        # exactly those two, plus mustExpress = the selected ids.
        facts = [f for f in case["stages"]["n1"]["facts"]
                 if f["factId"] in set(selected_ids)]
        plan = case["stages"]["organization"]["response"]
        row = {"rowId": f"comp:{cid}", "facts": facts,
               "mustExpress": list(selected_ids), "plan": plan}
        for probe_id, text, why in items:
            verdict = judge_row(row, text, "eos")
            probes.append({
                "probeId": probe_id, "caseId": cid, "text": text, "why": why,
                "rowId": row["rowId"],
                "gates": verdict["gates"],
                "problems": verdict["align"]["problems"],
                "residue": verdict["align"]["residue"],
                "pass": verdict["pass"],
            })

    synthetic = []
    for probe in SYNTHETIC:
        case = by_id[probe["caseId"]]
        base = {"facts": [f for f in case["stages"]["n1"]["facts"]
                          if f["factId"] in set(case["selectedFactIds"])],
                "mustExpress": list(case["selectedFactIds"]),
                "plan": case["stages"]["organization"]["response"]}
        synthetic.append({"probeId": probe["probeId"],
                          "caseId": probe["caseId"], "why": probe["why"],
                          "transform": probe["transform"],
                          "text": probe["text"], "synthetic": True,
                          **judge_synthetic(probe, base)})

    doc = {
        "version": "round-composition-contract-probes-v0.1",
        "purpose": "record how the frozen v2 N5 gate treats the two "
                   "contract conflicts (task-title quoting, exact time "
                   "value); no composition re-run, no model call",
        "runAt": datetime.now(timezone.utc).isoformat(),
        "sourceRun": {"path": str(pathlib.Path(args.run).relative_to(HERE)),
                      "sha256": sha256_file(args.run)},
        "rule": "eval_n4_v2.judge_row, same call as the composition archive",
        "probes": probes,
        "syntheticProbes": synthetic,
        "reading": {
            "taskTitle": "P1 passes because the v2 frame requires the goal "
                         "quoted as 「goal」; P2 paraphrases the same fact and "
                         "fails G1 (uncovered task_achieved). N4.0's "
                         "requirement line says 不写任务标题, so a text that "
                         "obeys N4.0 cannot pass the v2 gate for this fact.",
            "time": "P3 (vague) fails G3 with uncovered:f2:time; P4 with the "
                    "planned exact value passes. N4.0 renders time as "
                    "时间经过 / 过去了一会儿 and forbids 具体时长, so a "
                    "compliant text cannot pass G3.",
            "outcomeKind": "S1 converts the completed task into `outcome` + "
                           "resultText (the shape N2 selects and N4.0 packs) "
                           "and the judge raises 'no v2 pattern for kind "
                           "outcome'. So D1 option A needs a new N5 frame "
                           "before it can even be measured; the current gate "
                           "cannot express a verdict for that fact kind.",
        },
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    for p in probes:
        print(f"{p['probeId']:24s} pass={p['pass']} gates={p['gates']} "
              f"problems={p['problems']}")
    for p in synthetic:
        print(f"{p['probeId']:24s} pass={p['pass']} "
              f"{p.get('judgeError') or p.get('problems')}")
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
