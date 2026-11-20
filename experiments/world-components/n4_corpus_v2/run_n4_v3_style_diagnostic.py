# N4 v3 style diagnostic (N4 optimization experiment). Reads the frozen
# v3/v3a holdout rows and the eval archives; reports how many sentences the
# models actually produced per plan group and how many facts per sentence.
#
# This is a surface/style diagnostic, NOT a naturalness or quality gate: a
# lower sentence count is not automatically better. The hard gates remain
# the pass/fail authority.

import json
import pathlib
import statistics

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
CORPUS = HERE / "corpus_v3" / "holdout-v3.jsonl"
ARCH = REPO / "artifacts" / "world-components"
OUT = ARCH / "n4-v3-style-diagnostic.json"


def load_rows():
    return {json.loads(l)["rowId"]: json.loads(l) for l in
            CORPUS.read_text(encoding="utf-8").splitlines() if l.strip()}


def measure(name, rows):
    d = json.loads((ARCH / name).read_text(encoding="utf-8"))
    spg, fps = [], []
    total_sents = 0
    for c in d["test"]:
        r = rows[c["rowId"]]
        groups = len(r["plan"]["sentences"])
        facts = len(r["facts"])
        sents = c["output"].count("。")
        total_sents += sents
        if groups:
            spg.append(sents / groups)
        if sents:
            fps.append(facts / sents)
    return {
        "eval": name,
        "testHardPass": d["summary"]["testHardPass"],
        "testRows": d["summary"]["testRows"],
        "meanSentencesPerGroup": round(statistics.mean(spg), 3),
        "meanFactsPerSentence": round(statistics.mean(fps), 3),
        "totalSentences": total_sents,
    }


def targets(rows, corpus_report):
    report = json.loads((ARCH / corpus_report).read_text(encoding="utf-8"))
    return {
        "corpusReport": corpus_report,
        "meanSentencesPerGroup": report["targetStyle"]["v3"][
            "meanSentencesPerGroup"],
        "meanFactsPerSentence": report["targetStyle"]["v3"][
            "meanFactsPerSentence"],
        "totalSentences": report["targetStyle"]["v3"]["sentences"],
    }


def main() -> int:
    rows = load_rows()
    archive = {
        "purpose": "N4 v3 style diagnostic: surface shift under merged "
                   "same-entity targets; surface only, not a quality gate",
        "corpus": "corpus_v3/holdout-v3.jsonl",
        "rows": len(rows),
        "models": {
            "v2_on_v3_inputs": measure(
                "n4-v3-holdout-eval-v2model.json", rows),
            "v3a_oneFactTargets": measure(
                "n4-v3a-holdout-eval-v3amodel.json", rows),
            "v3b_mergedTargets": measure(
                "n4-v3-holdout-eval-v3model.json", rows),
        },
        "targets": {
            "merged_v3": targets(rows, "n4-v3-corpus-report.json"),
            "oneFact_v3a": {
                "corpusReport": "n4-v3a-corpus-report.json",
                "meanSentencesPerGroup": 1.667,
                "meanFactsPerSentence": 1.504,
                "totalSentences": 125,
            },
        },
        "finding": "The merged targets transferred: v3b emits ~1.03 "
                   "sentences per group and ~2.64 facts per sentence, close "
                   "to the merged target (1.04/2.41), versus ~1.72/1.68 for "
                   "the one-fact models. But v3b passes 62/66 hard gates vs "
                   "the old v2-on-v2 64/66, and the guard-on alternating row "
                   "still fails (v3b omits the middle task; v3a misattributes "
                   "it to the next actor). Style moved; hard fidelity did "
                   "not improve, so v3b is an experimental arm, not the "
                   "replacement default.",
    }
    OUT.write_text(json.dumps(archive, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(json.dumps(archive["models"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
