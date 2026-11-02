# N3 cross-group pronoun guard smoke with the real v2 N4 model (review
# round). This is a SMOKE, not a quality eval and not a holdout claim:
#
#   - rows come from the HISTORICAL v2 holdout (their facts are held fixed
#     so the N3 coref change is isolated; N1 is not re-run);
#   - the OLD plan is plan_v3(guard=False) and the NEW plan is
#     plan_v3(guard=True); fact groups/time must be identical;
#   - the real ckpt-v2 model generates from the NEW render input; the frozen
#     v2 gates judge the text.
#
# Pre-registered smoke gates:
#   S1 the guard removes at least one grant on the selected rows;
#   S2 fact groups/time are identical between old and new plans;
#   S3 every NEW output passes the v2 hard gates (G1/G2/G3/G4/G6);
#   S4 no row requires a model call over the 128-token limit.
#
# A pass means the safer input did not break these four rows. It does NOT
# establish N4 quality under guard-on at corpus scale.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(WC / "n4_corpus_v2"))

import n3_organize  # noqa: E402
from eval_n4_v2 import judge_row  # noqa: E402
from render_v2 import render_input_v2  # noqa: E402
from run_composition_v2 import V2N4  # noqa: E402

ROWS = [
    "v2-c-salt:cross-reference-8minute:v0",
    "v2-c-salt:alternating-6minute:v0",
    "v2-c-salt:core-move-task-c_wenrenjing-c_granary-5minute:v0",
    "v2-c-salt:conflict-shared-goal:v0",
]
OUT = REPO / "artifacts" / "world-components" / "n3-coref-guard-smoke-r1.json"


def names_of(row):
    names = {}
    for f in row["facts"]:
        if f.get("entityId") and f.get("name"):
            names.setdefault(f["entityId"], f["name"])
    return names


def grants(plan):
    return [[(g["refersTo"], g["pronoun"]) for g in s["coreference"]]
            for s in plan["sentences"]]


def shape(plan):
    return [(s["factIds"], s.get("time")) for s in plan["sentences"]]


def main() -> int:
    rows = {json.loads(l)["rowId"]: json.loads(l) for l in
            (WC / "n4_corpus_v2" / "corpus_v2" / "holdout-v2.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()}
    n4 = V2N4()
    cases, removed = [], 0
    for rid in ROWS:
        row = rows[rid]
        names, hints = names_of(row), row.get("genderHints") or {}
        old = n3_organize.plan_v3(row["facts"], names, hints,
                                  cross_group_guard=False)
        new = n3_organize.plan_v3(row["facts"], names, hints,
                                  cross_group_guard=True)
        old_grants, new_grants = grants(old), grants(new)
        removed += sum(len(a) - len(b) for a, b in zip(old_grants, new_grants))
        text = render_input_v2(new, row["facts"])
        input_tokens = len(n4.tok(text).input_ids)
        out = n4.generate(text)
        verdict = judge_row(row, out["text"], out["finishReason"])
        cases.append({
            "rowId": rid,
            "oldGrants": old_grants,
            "newGrants": new_grants,
            "groupsUnchanged": shape(old) == shape(new),
            "inputTokens": input_tokens,
            "renderText": text,
            "model": {"text": out["text"],
                      "finishReason": out["finishReason"],
                      "outputTokens": out["outputTokens"],
                      "wallMs": out["wallMs"]},
            "verdict": verdict,
        })
    archive = {
        "purpose": "N3 cross-group pronoun guard smoke with the real v2 N4 "
                   "model (review round): isolate the N3 coref change on "
                   "held-fixed historical rows and re-run the frozen gates",
        "scope": "SMOKE, not a quality eval/holdout; rows are the historical "
                 "v2 corpus (their facts are held fixed; N1 is not re-run)",
        "checkpoint": "experiments/world-components/n4_corpus_v2/ckpt-v2",
        "rows": ROWS,
        "cases": cases,
        "gates": {
            "S1_guardRemovesAGrant": removed > 0,
            "S2_factGroupsTimeUnchanged": all(c["groupsUnchanged"]
                                              for c in cases),
            "S3_newOutputsPassHardGates": all(c["verdict"]["pass"]
                                              for c in cases),
            "S4_withinTokenLimit": all(c["inputTokens"] <= 128
                                       for c in cases),
        },
        "summary": {"rows": len(cases), "grantsRemoved": removed,
                    "passed": sum(1 for c in cases if c["verdict"]["pass"])},
        "pass": (removed > 0
                 and all(c["groupsUnchanged"] for c in cases)
                 and all(c["verdict"]["pass"] for c in cases)),
    }
    OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps(archive["summary"], ensure_ascii=False),
          "pass:", archive["pass"], "->", OUT)
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
