"""Write the human-readable delivery note from the frozen reports.

All numbers come from `freeze.json`, `build-report.json`, `check.json` and
`index-report.json`; nothing is typed by hand, so the note cannot drift from the
artifact it describes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    out = Path(args.out_dir)
    freeze = json.loads((out / "freeze.json").read_text(encoding="utf-8"))
    build = json.loads((out / "build-report.json").read_text(encoding="utf-8"))
    check = json.loads((out / "check.json").read_text(encoding="utf-8"))
    index = json.loads((out / "index-report.json").read_text(encoding="utf-8"))

    positives = build["perGroupPositive"]
    zero = [group for group, count in positives.items() if count == 0]
    lines = [
        "# Short-pair delivery (13-way action-group judgement)",
        "",
        f"- pairs: **{freeze['pairs']}** ({freeze['decisions']} decisions, {freeze['positives']} positives)",
        f"- rows used: {index['counts']['rowsUsed']} of {index['counts']['rowsInFile']}; excluded: {index['counts']['rowsExcluded']}",
        f"- second-step pairs: {index['counts']['secondStepPairs']}",
        f"- indistinguishable texts (same label): {freeze['indistinguishableTexts']} (see `build-report.json`)",
        f"- label-conflicting texts: 0 (the build refuses them)",
        f"- tokens: p50 {check['tokens']['p50']} / p95 {check['tokens']['p95']} / p100 {check['tokens']['p100']}, "
        f"ceil32 {check['tokens']['ceil32']}, over 512: {check['tokens']['overMaxLen']}",
        f"- serializer: `{freeze['serializer']['version']}` sha256 `{freeze['serializer']['sha256']}` "
        f"(tracked={freeze['serializer']['tracked']}, dirty={freeze['serializer']['dirty']})",
        "",
        "## Positive count per candidate group",
        "",
        "| group | positives |",
        "|---|---|",
    ]
    for group, count in positives.items():
        lines.append(f"| {group} | {count} |")
    lines += [
        "",
        f"Groups with zero positives (negatives only, unlearnable in this set): {', '.join(zero) or 'none'}.",
        "",
        "## Omission totals",
        "",
        "| what | count |",
        "|---|---|",
    ]
    for key, value in (build.get("omittedTotals") or {}).items():
        lines.append(f"| {key} | {value} |")
    lines += [
        "",
        "## Files",
        "",
    ]
    for name, digest in freeze["files"].items():
        lines.append(f"- `{name}` sha256 `{digest}`")
    lines += [
        "",
        "## Reproduce",
        "",
        "```bash",
        "cd experiments/action-dataset-v1",
        "python -X utf8 short_pairs/pair_index.py --rows rows/train13-full-candidates.jsonl \\",
        "  --labels ../../../results/action-dataset-20261111/labels-v1.json \\",
        "  --resolution ../../../results/action-short-pairs-20261111/01-shortx-exclusions.json \\",
        "  --out-dir short_pairs/out",
        "python -X utf8 short_pairs/build_pairs.py --rows rows/train13-full-candidates.jsonl \\",
        "  --index short_pairs/out/pairs-index.jsonl --out-dir short_pairs/out \\",
        "  --allow-same-label-duplicates",
        "python -X utf8 short_pairs/check_pairs.py --rows rows/train13-full-candidates.jsonl \\",
        "  --pairs short_pairs/out/pairs.jsonl --out short_pairs/out/check.json",
        "python -X utf8 short_pairs/freeze.py --out-dir short_pairs/out \\",
        "  --rows rows/train13-full-candidates.jsonl \\",
        "  --exclusions ../../../results/action-short-pairs-20261111/01-shortx-exclusions.json",
        "```",
        "",
        f"Source rows sha256 `{freeze['rows']['sha256']}` (the frozen 300-row file, unchanged).",
        f"Model snapshot config `{freeze['model']['configSha256']}`, vocab `{freeze['model']['vocabSha256']}`, "
        f"max_position_embeddings {freeze['model']['maxPositionEmbeddings']}.",
        "",
        "This is a training-input freeze, not a model result. The second step is teacher-forced: it keeps the",
        "original X and only adds `已做`, so it is not yet evidence of the settled next state.",
    ]
    (out / "delivery.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print("wrote", out / "delivery.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
