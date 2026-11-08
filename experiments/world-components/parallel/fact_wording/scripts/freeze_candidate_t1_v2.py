"""Freeze candidate T1 v2: same template change, completed admission criteria.

v1 (freeze/candidate-t1-v1.json) stays untouched. v2 re-derives every T1 input,
checks it still equals the v1 hashes, and records the pre-registered rules that will
decide whether T1 may go on to the 17-unit acceptance set.
"""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve()
EXPERIMENT = HERE.parents[1]
TREE = HERE.parents[5]
UNIT_FILE = TREE / "artifacts/world-components/n4-cf24-contract.jsonl"
V1 = EXPERIMENT / "freeze/candidate-t1-v1.json"
OUT = EXPERIMENT / "freeze/candidate-t1-v2.json"

CRITERIA = {
    "C1_additions_fixed": dict(
        threshold=">= 3 of the 6 r1 extra_action_state units",
        valid_fix="the added content disappears AND the fact stays complete AND no other category fires",
        units=["t07:f0", "t07:f1", "t11:f0", "t12:f0", "t15:f0", "t17:f0"],
    ),
    "C2_no_regression_of_passes": dict(
        rule="any unit that passed under greedy in r1 must not become fail or undetermined",
        categories="all seven; a new category on a formerly passing unit fails this criterion",
    ),
    "C3_no_u_to_fail": dict(
        rule="a unit judged undetermined in r1 must not become fail (staying U or becoming pass is allowed)",
        units=["t10:f3", "t14:f0", "t16:f2", "t18:f0"],
    ),
    "C4_fact_components_kept": dict(
        rule="actions, states and positions that the fact itself contains must not be omitted",
        measure="per unit: resultText/from-to/direction content must all be present; omission = fact_not_expressed flag",
    ),
    "verdict": "all four must hold; otherwise T1 is recorded as failed and no prompt is re-tuned",
}


def sha_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    v1 = json.loads(V1.read_text(encoding="utf-8"))
    units = [json.loads(line) for line in UNIT_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    v1_by_id = {row["unitId"]: row for row in v1["rows"]}

    rows, mismatches = [], []
    for unit in units:
        new_input = unit["input"].replace(v1["oldRequirement"], v1["newRequirement"])
        occurrences = unit["input"].count(v1["oldRequirement"])
        new_hash = sha(new_input)
        expected = v1_by_id[unit["unitId"]]["newInputSha256"]
        ok = occurrences == 1 and new_hash == expected
        if not ok:
            mismatches.append(dict(unitId=unit["unitId"], occurrences=occurrences,
                                   newHash=new_hash, expected=expected))
        rows.append(dict(unitId=unit["unitId"], oldInputSha256=sha(unit["input"]),
                         newInputSha256=new_hash, rederivedMatchesV1=ok))

    payload = dict(
        protocol="c4-candidate-t1-v2",
        status="frozen; approved for the 85-unit greedy diagnostic; acceptance set not run",
        supersedes="freeze/candidate-t1-v1.json",
        v1Sha256=sha_bytes(V1),
        change=dict(
            scope="every one of the 85 cf24 inputs; one clause of the requirement sentence",
            oldRequirement=v1["oldRequirement"],
            newRequirement=v1["newRequirement"],
            oldRequirementSha256=sha(v1["oldRequirement"]),
            newRequirementSha256=sha(v1["newRequirement"]),
            untouched=["facts", "visible lists", "scenes", "viewers", "directions", "everything else in the template"],
        ),
        verification=dict(
            units=len(units), rederivedMatchesV1=sum(1 for r in rows if r["rederivedMatchesV1"]),
            mismatches=mismatches,
            unitFile=str(UNIT_FILE.relative_to(TREE)).replace(chr(92), "/"),
            unitFileSha256=sha_bytes(UNIT_FILE),
        ),
        runPlan=dict(
            scheme="T1 greedy only",
            units=85,
            reference="r1 greedy rows in artifacts/fact-wording/diagnostic-r1/*/raw.jsonl",
            decode="greedy, 20 s, 64 new tokens, CPU fp32, 4 threads (protocol v3)",
            runDirectory="artifacts/fact-wording/diagnostic-r2-cand-t1/<runId>/",
            selfSnapshot="the runner copies itself into the run directory and re-hashes at the end",
            editsDuringRun="forbidden; the self-snapshot hash must match at start and end",
        ),
        admissionCriteria=CRITERIA,
        reporting=dict(
            main="all 85 units, paired r1 greedy vs T1 greedy under the same blind judging",
            sensitivity="repeat the main table without t12:f2 and t24:f3 (known input/fact conflicts)",
            perDefect="the six r1 addition units, unit by unit",
            regressions="every unit that got worse, with categories",
            strata="seen-fact vs independent using cf24-overlap.json labels",
            timing="descriptive for this round only; cross-session differences are not attributed to T1",
        ),
        rows=rows,
    )
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"units={len(units)} rederived_matches_v1={payload['verification']['rederivedMatchesV1']} "
          f"mismatches={len(mismatches)}")
    print("v2:", OUT)
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
