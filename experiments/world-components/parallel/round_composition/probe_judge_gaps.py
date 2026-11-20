"""Probe the four N5 (judge_v3) defects the owner derived from the code.

The owner's review listed them as risks read off the source, not as reproduced
failures. This script turns each one into an executable counter-example and,
separately, measures what the same behaviour did to the three archived real
batches (v1, v2, v3). It does not change the judge: the judge is frozen, and
fixing it is a separate ruling.

Outputs (written by --write):
  out/judge-gaps-probes.json   machine-readable verdicts + archive impact
  out/judge-gaps-probes.log    the same, human-readable

Usage: python -X utf8 probe_judge_gaps.py [--write]
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
for p in (HERE, HERE.parent.parent, HERE.parent.parent / "n4_input_renderer",
          HERE.parent.parent / "n4_corpus_v2"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import judge_v3  # noqa: E402

PA = {"factId": "f0", "kind": "moved", "entityId": "char_pa", "name": "管线甲",
      "entityGroup": "characters", "from": "管线镇", "to": "钟楼"}
PA_OUT = {"factId": "f1", "kind": "outcome", "entityId": "char_pa",
          "name": "管线甲", "entityGroup": "characters",
          "resultText": "把铜铃挂回了钟楼"}
PA_OUT2 = {"factId": "f2", "kind": "outcome", "entityId": "char_pa",
           "name": "管线甲", "entityGroup": "characters",
           "resultText": "松开了手"}  # deliberately short, easy to embed

YI1 = {"factId": "g0", "kind": "moved", "entityId": "char_y1", "name": "管线乙",
       "entityGroup": "characters", "from": "管线镇", "to": "钟楼"}
YI2 = {"factId": "g1", "kind": "moved", "entityId": "char_y2", "name": "管线乙",
       "entityGroup": "characters", "from": "钟楼", "to": "广场"}


def run(facts, must, text, finish="stop"):
    try:
        j = judge_v3.judge(facts, must, None, text, finish)
    except judge_v3.JudgeBlocked as exc:
        return {"blocked": exc.code, "detail": exc.detail}
    return {"hardPass": j["hardPass"], "gates": j["gates"],
            "problems": j["problems"], "covered": j["covered"],
            "residue": j["residue"], "status": j["status"]}


def probe(pid, claim, text, facts, must, finish="stop", desired="reject"):
    """`desired` is what a correct judge should do with this text. A defect is
    reproduced when the frozen judge does the opposite."""
    got = run(facts, must, text, finish)
    passed = bool(got.get("hardPass"))
    reproduced = (not passed) if desired == "pass" else passed
    return {"id": pid, "claim": claim, "text": text,
            "facts": [f["factId"] for f in facts], "finishReason": finish,
            "desired": desired, "observed": got,
            "defectReproduced": reproduced}


PROBES = [
    probe(
        "P1-g2-repeated-registered-name",
        "G2 rejects a registered character's name outside the matched fact span "
        "even though the mention adds no event",
        "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。"
        "管线甲在窗边站定，望着远处的塔尖，没有说话。",
        [PA, PA_OUT], ["f0", "f1"], desired="pass"),
    probe(
        "P2-g2-scope-unregistered-name",
        "G2 does not look at names that are not in the registry, so an invented "
        "actor is invisible to the hard gates (D4/N6 must catch it)",
        "王五站在门口，看着管线甲把铜铃挂回了钟楼。",
        [PA, PA_OUT], ["f1"]),
    probe(
        "P3-g1-negated-result",
        "G1 accepts a negated result because up to 8 characters may sit between "
        "the subject and the result text",
        "管线甲并未把铜铃挂回了钟楼，他只是站在楼梯口看了一会儿。",
        [PA_OUT], ["f1"]),
    probe(
        "P4-g1-hedged-result",
        "G1 accepts a hedged/unrealised result ('差点就') for the same reason",
        "管线甲差点就把铜铃挂回了钟楼，手抖了一下又缩了回去。",
        [PA_OUT], ["f1"]),
    probe(
        "P5-g1-observer-attribution",
        "G1 cannot tell the actor from an observer when the result text follows "
        "the named subject",
        "王五看见管线甲把铜铃挂回了钟楼。",
        [PA_OUT], ["f1"]),
    probe(
        "P6-g4-count-only",
        "G4 only counts occurrences of the shared name, so one person described "
        "twice satisfies the two-actor condition",
        "管线乙从管线镇来到了钟楼。管线乙从钟楼来到了广场。",
        [YI1, YI2], ["g0", "g1"]),
    probe(
        "P7-g6-missing-finish-reason",
        "G6 treats a missing finish reason as a normal stop (the runner maps "
        "null to 'eos'), so truncation cannot be detected without done_reason",
        "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。",
        [PA, PA_OUT], ["f0", "f1"], finish=None),
    probe(
        "P8-g6-length",
        "control: a length-capped call is rejected",
        "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了钟楼。",
        [PA, PA_OUT], ["f0", "f1"], finish="length", desired="reject"),
    probe(
        "P9-g1-wrong-result",
        "control: the same frame rejects a different result",
        "管线甲从管线镇来到了钟楼。管线甲把铜铃挂回了城门口。",
        [PA, PA_OUT], ["f0", "f1"], desired="reject"),
    probe(
        "P10-g2-goal-leak",
        "control: a task goal repeated outside the matched span is still caught",
        "管线甲从管线镇来到了钟楼。任务「把铜铃挂回原位」还没有结束。",
        [PA, {"factId": "f9", "kind": "task_achieved", "entityId": "char_pa",
              "name": "管线甲", "entityGroup": "characters",
              "goal": "把铜铃挂回原位"}],
        ["f0", "f9"], desired="reject"),
]

# P10 needs the goal text on a fact; G2 reads goals from the facts, so a goal
# that exists only in the game state is invisible to it.



def archive_impact():
    """Re-judge the archived first calls and count what the probe defects did."""
    import real_batch_v3 as rb  # frozen runner; importing has no side effects

    cases_doc = json.loads(
        (HERE / "fixtures" / "batch-v1-cases.json").read_text(encoding="utf-8"))
    by_id = {c["caseId"]: c for c in cases_doc["cases"]}
    out = {}
    for name in ("real-batch-v1", "real-batch-v2", "real-batch-v3"):
        run_doc = json.loads((HERE / "out" / f"{name}.json")
                             .read_text(encoding="utf-8"))
        rows = []
        for case in run_doc["cases"]:
            cid = case["caseId"]
            chain = rb.build_chain(by_id[cid])
            facts = chain["n1Facts"]
            must = [f["factId"] for f in chain["selected"]]
            text = case["attempts"][0]["output"]
            finish = case["attempts"][0]["finishReason"]
            res = run(facts, must, text, finish or "eos")
            gates = res.get("gates") or {}
            probs = res.get("problems") or []
            residue_names = [p for p in probs if p.startswith("residue-name:")]
            non_residue = [p for p in probs if not p.startswith("residue-")]
            # how much of each outcome match is connective prose, and does it
            # carry a negation/hedge?
            outcome_gaps = []
            for f in chain["selected"]:
                if f.get("kind") != "outcome":
                    continue
                pat = judge_v3._patterns_for(f, None)[0]
                for m in re.finditer(pat, text):
                    inner = m.group(0)[len(f["name"]):]
                    gap = inner[:inner.rfind(f["resultText"].strip())] \
                        if f["resultText"].strip() in inner else ""
                    outcome_gaps.append({
                        "gap": gap,
                        "negated": bool(re.search(r"未|没|不|别|勿|差点", gap)),
                        "covered": f["factId"] in res.get("covered", []),
                    })
            rows.append({
                "caseId": cid,
                "hardPass": res.get("hardPass"),
                "gates": gates,
                "residueNames": residue_names,
                "problemsWithoutResidue": non_residue,
                "wouldPassIfResidueIgnored": bool(
                    gates and all(v for k, v in gates.items()
                                  if k != "G2_residue")),
                "outcomeGaps": outcome_gaps,
            })
        out[name] = {
            "samples": rows,
            "residueFlaggedSamples": sum(1 for r in rows if r["residueNames"]),
            "residueFlags": sum(len(r["residueNames"]) for r in rows),
            "wouldPassIfResidueIgnored": sum(
                1 for r in rows if r["wouldPassIfResidueIgnored"]),
            "coveredOutcomes": sum(1 for r in rows
                                   for g in r["outcomeGaps"] if g["covered"]),
            "coveredOutcomesWithGap": sum(
                1 for r in rows for g in r["outcomeGaps"]
                if g["covered"] and g["gap"]),
            "coveredOutcomesWithNegation": sum(
                1 for r in rows for g in r["outcomeGaps"]
                if g["covered"] and g["negated"]),
        }
    return out


def main() -> int:
    impact = archive_impact()
    doc = {"version": "judge-gaps-probes", "judge": judge_v3.VERSION,
           "probes": PROBES, "archiveImpact": impact,
           "note": "The judge was NOT modified. Each probe records what the "
                   "frozen judge does with a hand-written counter-example."}
    lines = [f"# judge_v3 gap probes ({judge_v3.VERSION})", ""]
    for p in PROBES:
        obs = p["observed"]
        lines.append(f"{p['id']}: "
                     + ("DEFECT REPRODUCED" if p["defectReproduced"]
                        else "not reproduced"))
        lines.append(f"  claim   : {p['claim']}")
        lines.append(f"  text    : {p['text']}")
        lines.append(f"  desired : {p['desired']}")
        lines.append(f"  gates   : {json.dumps(obs.get('gates'), ensure_ascii=False)}")
        lines.append(f"  problems: {obs.get('problems')}")
        lines.append("")
    lines.append("# archived first calls re-judged")
    for name, v in impact.items():
        lines.append(f"{name}: residue-flagged samples "
                     f"{v['residueFlaggedSamples']}/10, flags {v['residueFlags']}, "
                     f"would pass if residue ignored {v['wouldPassIfResidueIgnored']}, "
                     f"covered outcomes {v['coveredOutcomes']} "
                     f"(with gap {v['coveredOutcomesWithGap']}, "
                     f"negated {v['coveredOutcomesWithNegation']})")
    text = "\n".join(lines) + "\n"
    if "--write" in sys.argv:
        (HERE / "out" / "judge-gaps-probes.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        (HERE / "out" / "judge-gaps-probes.log").write_text(
            text, encoding="utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
