"""Recompute the v1 six-condition table with the no-attention baseline.

This reads the frozen v1 JSON (never modifies it) and applies the same
no-attention rule used in v2: keep every must, drop forbidden/uncertain/
already-narrated/time/no_change, keep every remaining optional. It also
re-scores the v1 rule's recorded selection and the legacy mustPrecision.
The point is to verify the reviewer's observation: the v1 6/6 is reproducible
without reading attention, because each v1 condition's prior removes the
competing optional.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import selector

HERE = Path(__file__).resolve().parent
V1 = HERE.parents[3] / "artifacts/world-components/organize-wording/attention-selection-v1.json"


def sha256(path: Path) -> str:
    """Use the committed blob when the file is tracked; CRLF checkouts differ."""
    try:
        rel = path.resolve().relative_to(HERE.parents[3]).as_posix()
        blob = subprocess.run(["git", "show", "HEAD:" + rel], cwd=HERE.parents[3],
                              capture_output=True, check=True).stdout
        return hashlib.sha256(blob).hexdigest()
    except Exception:
        return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--v1", type=Path, default=V1)
    parser.add_argument("--out", type=Path,
                        default=HERE.parents[3] / "artifacts/world-components/parallel/fact-selection-v2/v1-recheck.json")
    args = parser.parse_args()
    old = json.loads(args.v1.read_text(encoding="utf-8"))
    rows = []
    for group in old["groups"]:
        must = {fact["factId"] for fact in group["facts"] if fact["authorization"] == "must"}
        for condition in group["conditions"]:
            case = {
                "caseId": condition["conditionId"],
                "facts": group["facts"],
                "alreadyNarratedFactIds": condition["alreadyNarratedFactIds"],
                "manualSelectedFactIds": condition["manualSelectedFactIds"],
                "targetOptionalFactIds": sorted(set(condition["manualSelectedFactIds"]) - must),
                "relatedOptionalFactIds": [],
            }
            no_attn = selector.select_no_attention(case)
            old_rule = condition["ruleSelectedFactIds"]
            rows.append({
                "caseId": condition["conditionId"],
                "groupId": group["groupId"],
                "attention": condition["attention"],
                "prior": condition["alreadyNarratedFactIds"],
                "manual": condition["manualSelectedFactIds"],
                "noAttention": no_attn,
                "noAttentionEqualManual": set(no_attn) == set(condition["manualSelectedFactIds"]),
                "noAttentionScore": selector.evaluate(case, no_attn),
                "v1Rule": old_rule,
                "v1RuleEqualManual": set(old_rule) == set(condition["manualSelectedFactIds"]),
                "v1RuleScore": selector.evaluate(case, old_rule),
            })
    no_attn_pass = sum(1 for row in rows if row["noAttentionEqualManual"])
    old_pass = sum(1 for row in rows if row["v1RuleEqualManual"])
    out = {
        "protocol": "attention-selection-v1-recheck",
        "source": {"file": str(args.v1), "sha256": sha256(args.v1)},
        "rule": "keep all must; drop forbidden/uncertain/prior/time/no_change; keep every remaining optional; ignore attention",
        "summary": {
            "conditions": len(rows),
            "noAttentionEqualManual": no_attn_pass,
            "v1RuleEqualManual": old_pass,
            "noAttentionHardPass": sum(1 for row in rows if row["noAttentionScore"]["hardPass"]),
            "noAttentionMustPrecisionMean": sum(row["noAttentionScore"]["mustPrecision"] for row in rows) / len(rows),
            "v1RuleMustPrecisionMean": sum(row["v1RuleScore"]["mustPrecision"] for row in rows) / len(rows),
            "allMustPrecisionBelow085": all(row["noAttentionScore"]["mustPrecision"] < 0.85 for row in rows),
        },
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    print(f"v1 {len(rows)} conditions; no-attention equal manual {no_attn_pass}/{len(rows)}; "
          f"v1 rule equal manual {old_pass}/{len(rows)}")
    print(f"no-attention mustPrecision mean {out['summary']['noAttentionMustPrecisionMean']:.3f}; "
          f"v1 rule mustPrecision mean {out['summary']['v1RuleMustPrecisionMean']:.3f}; "
          f"all below 0.85: {out['summary']['allMustPrecisionBelow085']}")
    for row in rows:
        print(f"  {row['caseId']}: no-attn {row['noAttention']} {'=' if row['noAttentionEqualManual'] else '!='} "
              f"manual {row['manual']}; prior {row['prior']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
