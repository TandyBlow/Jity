# Record the N4.0 legacy sentence-renderer regression evidence.
#
# Run after test_renderer.py passes:
#   python -X utf8 experiments/world-components/n4_input_renderer/record_evidence.py
#
# The artifact records source digests, the 12+12 byte-identical regression,
# and the fail-closed unit cases. It does not call a model.

import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(WC))

import test_renderer as tests  # noqa: E402
from n4_input_renderer import renderer  # noqa: E402

OUT = REPO / "artifacts" / "world-components" / "n4-input-renderer-r1.json"

SOURCES = [
    "experiments/world-components/n4_input_renderer/renderer.py",
    "experiments/world-components/n4_input_renderer/scene_context.py",
    "experiments/world-components/n4_input_renderer/test_renderer.py",
    "experiments/world-components/n4_narrative_dev/render_narrative.py",
    "experiments/world-components/n4_narrative_dev/build_scene_context.py",
    "experiments/world-components/n4_narrative_dev/corpus.jsonl",
    "experiments/world-components/n4_narrative_dev/world.json",
    "experiments/world-components/n4_narrative_dev/pipeline_preview.json",
    "experiments/world-components/n4_narrative_dev/input_preview.json",
    "design/world-engine-reports/components/n4-input-packing.md",
]

UNITS = [
    "test_missing_environment_is_omitted",
    "test_time_amount_never_rendered",
    "test_global_time_fallback",
    "test_goal_never_rendered",
    "test_plan_order_is_authoritative",
    "test_fail_closed",
    "test_orchestrator_and_determinism",
]


def sha(rel):
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def git_head():
    out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def main():
    count = tests.test_corpus_regression()
    for name in UNITS:
        getattr(tests, name)()
    payload = {
        "component": "N4.0-legacy-sentence",
        "name": "legacy sentence-row renderer",
        "role": "legacy path for frozen v2/v3 models; not the current N4 input contract",
        "version": renderer.N4_VERSION,
        "date": "2026-11-02",
        "parentCommit": git_head(),
        "numbering": {
            "N4": "input-render",
            "N5": "generation (old N4)",
            "N6": "verification (old N5)",
        },
        "regression": {
            "groupedCases": count,
            "flatCases": count,
            "byteIdentical": True,
        },
        "units": UNITS,
        "failClosedCodes": [
            "plan-shape-invalid", "plan-unknown-fact", "duplicate-fact",
            "selected-unknown-fact", "plan-coverage-mismatch",
            "unsupported-fact-kind", "outcome-result-missing", "missing-field",
            "world-location-missing", "world-location-appearance-missing",
            "world-item-missing", "world-item-appearance-missing",
            "world-character-missing", "character-name-missing",
            "character-personality-missing", "character-appearance-missing",
            "scene-location-path-missing", "perspective-unresolved",
        ],
        "notes": [
            "Grouped and flat previews are byte-identical to the approved "
            "12-case corpus before the N4 extraction.",
            "No model call; the renderer is deterministic and program-only.",
            "Old dev files render_narrative.py/build_scene_context.py are "
            "compatibility shims over this component.",
            "Known gaps: wind/light/atmosphere not rendered; held items are "
            "also listed as visible; WorldState.Task has no resultText yet.",
        ],
        "sources": {rel: sha(rel) for rel in SOURCES},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"N4 evidence: {OUT}")
    print(f"parent: {payload['parentCommit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
