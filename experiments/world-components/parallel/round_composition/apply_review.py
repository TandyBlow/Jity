# Merge D4 labels and N6 verdicts into a real-batch archive.
#
# The run archive holds raw model output and starts with d4 unchecked (count
# null) and n6 not-run. This script writes a SEPARATE reviewed archive: it copies
# the run, attaches the labels/verdicts from the review file, and computes
# `quality` with judge_v3.quality so that a sample is a quality pass only when an
# executed N6 says pass.
#
# The raw run archive is never modified, so a reader can always see the
# unreviewed state and the exact texts the review refers to.
#
# Usage:
#   python -X utf8 apply_review.py                     # v1 defaults
#   python -X utf8 apply_review.py --run out/real-batch-v2.json \
#       --review fixtures/review-v2.json \
#       --out out/real-batch-v2-reviewed.json

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import judge_v3  # noqa: E402

# All three paths are required: the v1 reviewed archive is a closed record and
# must not be regenerated with newer fields by accident.
DEFAULTS = {
    "run": HERE / "out" / "real-batch-v1.json",
    "review": HERE / "fixtures" / "review-v1.json",
    "out": HERE / "out" / "real-batch-v1-reviewed.json",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", required=True)
    ap.add_argument("--review", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    run = json.loads(pathlib.Path(args.run).read_text(encoding="utf-8"))
    review = json.loads(pathlib.Path(args.review).read_text(encoding="utf-8"))
    if review["batchId"] != run["batchId"]:
        raise SystemExit("review and run belong to different batches")
    reviewed = review["cases"]

    missing = [c["caseId"] for c in run["cases"] if c["caseId"] not in reviewed]
    if missing:
        raise SystemExit(f"samples without a review: {missing}")

    quality_counts = {}
    for case in run["cases"]:
        entry = reviewed[case["caseId"]]
        annotations = (entry.get("d4") or {}).get("annotations")
        d4 = judge_v3.unregistered_names(annotations)
        d4["text"] = entry.get("text")
        d4["errors"] = [i for i in d4["items"] if i.get("isError")]
        d4["quotedFromAuthority"] = [i for i in d4["items"]
                                     if not i.get("isError")]
        case["d4"] = d4
        n6 = dict(entry.get("n6") or {"status": "not-run"})
        n6["reviewer"] = review["reviewer"]
        n6["reviewStatus"] = review["reviewStatus"]
        n6["reviewedAt"] = review["reviewedAt"]
        case["n6"] = n6
        case["quality"] = judge_v3.quality(n6)
        # the review is bound to one attempt; later attempts (retries) are
        # archived but not reviewed, so their quality stays pending
        reviewed_attempt = review.get("reviewedAttempt", 1)
        case["reviewedAttempt"] = reviewed_attempt
        case["qualityPrimary"] = case["quality"]
        case["qualityFinal"] = ("pending"
                               if len(case["attempts"]) > reviewed_attempt
                               else case["quality"])
        quality_counts[case["quality"]] = quality_counts.get(
            case["quality"], 0) + 1
        if entry.get("text") and case["attempts"]:
            reviewed_att = case["attempts"][reviewed_attempt - 1]
            if entry["text"] != reviewed_att.get("output"):
                raise SystemExit(f"{case['caseId']}: reviewed text is not the "
                                 f"output of attempt {reviewed_attempt}")

    run["review"] = {
        "source": f"fixtures/{pathlib.Path(args.review).name}",
        "reviewer": review["reviewer"],
        "reviewStatus": review["reviewStatus"],
        "reviewedAt": review["reviewedAt"],
        "scope": review["scope"],
        "d4Rule": review["d4Rule"],
        "n6Rule": review["n6Rule"],
        "summary": review["summary"],
    }
    s = run["summary"]
    s["quality"] = quality_counts
    s["qualityPassed"] = quality_counts.get("pass", 0)
    s["qualityFailed"] = quality_counts.get("fail", 0)
    s["qualityUndetermined"] = quality_counts.get("undetermined", 0)
    s["qualityPending"] = quality_counts.get("pending", 0)
    s["d4Labeled"] = sum(1 for c in run["cases"] if c["d4"]["checked"])
    s["d4LabelCount"] = sum(c["d4"]["count"] or 0 for c in run["cases"])
    s["d4Inventions"] = sum(len(c["d4"]["errors"]) for c in run["cases"])
    s["reviewedAttempt"] = review.get("reviewedAttempt", 1)
    s["qualityPrimary"] = {k: v for k, v in quality_counts.items()}
    s["qualityFinalPending"] = sum(1 for c in run["cases"]
                                   if c.get("qualityFinal") == "pending")
    run["caveat"] = (
        "n5-pass means the hard gates passed only. quality comes from the N6 "
        "review attached here; an n5 failure is never a quality pass. The "
        "program-template fallbacks are recorded per sample but are not model "
        "output and are not reviewed.")
    run["version"] = run["version"].replace("-run", "-reviewed")

    pathlib.Path(args.out).write_text(
        json.dumps(run, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    print(f"quality={quality_counts} d4Labeled={s['d4Labeled']} "
          f"labels={s['d4LabelCount']} inventions={s['d4Inventions']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
