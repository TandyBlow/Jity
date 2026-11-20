# N3 cross-group pronoun guard impact on the committed v2 plans (review
# round). This is a regression/impact record, not a quality evaluation:
#
#   guard ON  : plan_v3(..., cross_group_guard=True)
#   guard OFF : the legacy convention that produced the committed corpus
#
# Assertions (pre-registered here):
#   I1 with the guard ON, the FACT GROUPS and TIME attribution are identical
#      to the committed plans for every row (the guard may only remove
#      pronoun grants, never regroup or move time);
#   I2 with the guard OFF, the full plan (groups, time, grants) reproduces
#      the committed plans exactly;
#   I3 the guard ON changes at least one coreference grant (otherwise the
#      guard is dead code and the claim is void).
#
# The changed rows are listed so the v2 corpus/eval/model inputs can be
# marked as the legacy guard-off convention.

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(WC))

import n3_organize  # noqa: E402

CORPUS = WC / "n4_corpus_v2" / "corpus_v2"
OUT = REPO / "artifacts" / "world-components" / "n3-coref-guard-impact-r1.json"


def names_of(row):
    names = {}
    for f in row["facts"]:
        if f.get("entityId") and f.get("name"):
            names.setdefault(f["entityId"], f["name"])
    return names


def shape(plan):
    return [(s["factIds"], s.get("time")) for s in plan["sentences"]]


def coref(plan):
    return [(i, tuple(sorted((g["refersTo"], g["pronoun"])
                             for g in s["coreference"])))
            for i, s in enumerate(plan["sentences"])]


def main() -> int:
    rows = []
    for split in ("train-v2.jsonl", "holdout-v2.jsonl"):
        rows += [json.loads(l) for l in
                 (CORPUS / split).read_text(encoding="utf-8").splitlines()
                 if l.strip()]
    group_diffs, coref_diffs, legacy_diffs = [], [], []
    for row in rows:
        names, hints = names_of(row), row.get("genderHints") or {}
        stored = row["plan"]
        on = n3_organize.plan_v3(row["facts"], names, hints,
                                cross_group_guard=True)
        off = n3_organize.plan_v3(row["facts"], names, hints,
                                  cross_group_guard=False)
        if shape(on) != shape(stored):
            group_diffs.append(row["rowId"])
        if coref(on) != coref(stored):
            coref_diffs.append(row["rowId"])
        if (shape(off), coref(off)) != (shape(stored), coref(stored)):
            legacy_diffs.append(row["rowId"])
    archive = {
        "purpose": "N3 cross-group pronoun guard impact on the committed v2 "
                   "plans (review round)",
        "guard": "plan_v3(cross_group_guard=True) denies a grant when the "
                 "previous group has a different entity with the same "
                 "pronoun; guard=False is the legacy v2 convention",
        "scope": "impact/regression record, not a naturalness or N4 quality "
                 "evaluation; changed rows are legacy coref inputs",
        "corpus": {
            "train": "experiments/world-components/n4_corpus_v2/corpus_v2/"
                     "train-v2.jsonl",
            "holdout": "experiments/world-components/n4_corpus_v2/corpus_v2/"
                       "holdout-v2.jsonl",
            "rows": len(rows),
        },
        "impact": {
            "groupTimeDiffsGuardOn": len(group_diffs),
            "corefDiffsGuardOn": len(coref_diffs),
            "fullPlanDiffsGuardOff": len(legacy_diffs),
            "corefChangedRowIds": coref_diffs,
            "groupTimeChangedRowIds": group_diffs,
            "legacyChangedRowIds": legacy_diffs,
        },
        "gates": {
            "I1_groupTimeUnchangedGuardOn": not group_diffs,
            "I2_legacyOffReproducesCommitted": not legacy_diffs,
            "I3_guardChangesAtLeastOneGrant": bool(coref_diffs),
        },
        "pass": (not group_diffs) and (not legacy_diffs) and bool(coref_diffs),
    }
    OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps(archive["impact"] | {"corefChangedRowIds": None},
                     ensure_ascii=False))
    print("pass:", archive["pass"], "->", OUT)
    return 0 if archive["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
