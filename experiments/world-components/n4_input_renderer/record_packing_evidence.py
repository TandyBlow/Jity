# Record the N4.0 structured input packing evidence.
#
# Run: python -X utf8 experiments/world-components/n4_input_renderer/record_packing_evidence.py
#
# Records source digests, the 12-case pack regression, token counts, and the
# fail-closed cases. It does not call a model.

import hashlib
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
REPO = WC.parent.parent
sys.path.insert(0, str(WC))

import test_packer as tests  # noqa: E402
from n4_input_renderer import N4_INPUT_VERSION, pack_narrative_input  # noqa: E402

OUT = REPO / "artifacts" / "world-components" / "n4-input-packing-r1.json"
DEV = WC / "n4_narrative_dev"

SOURCES = [
    "experiments/world-components/n4_input_renderer/packer.py",
    "experiments/world-components/n4_input_renderer/scene_context.py",
    "experiments/world-components/n4_input_renderer/renderer.py",
    "experiments/world-components/n4_input_renderer/test_packer.py",
    "experiments/world-components/n4_input_renderer/test_renderer.py",
    "experiments/world-components/n4_narrative_dev/pipeline_narrative.py",
    "experiments/world-components/n4_narrative_dev/preview_pack_inputs.py",
    "experiments/world-components/n4_narrative_dev/corpus.jsonl",
    "experiments/world-components/n4_narrative_dev/world.json",
    "experiments/world-components/n4_narrative_dev/pipeline_preview.json",
    "experiments/world-components/n4_narrative_dev/pack_preview.json",
    "design/world-engine-reports/components/n4-input-packing.md",
    "design/world-engine-reports/components/n4-narrative-input-packing-preview.md",
]

UNITS = [
    "test_12_case_pack",
    "test_records_not_sentences",
    "test_fail_closed",
]


def sha(rel):
    return hashlib.sha256((REPO / rel).read_bytes()).hexdigest()


def git_head():
    out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip()


def token_counts():
    from transformers.models.t5.tokenization_t5 import T5Tokenizer
    tok = T5Tokenizer.from_pretrained(
        str(WC / "n4_corpus_v2" / "ckpt-v2"), legacy=False)
    world = json.loads((DEV / "world.json").read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in
             (DEV / "corpus.jsonl").read_text(encoding="utf-8").splitlines()
             if line.strip()]
    rows = json.loads((DEV / "pipeline_preview.json").read_text(encoding="utf-8"))["cases"]
    counts = []
    for case, row in zip(cases, rows):
        selected = [d["factId"] for d in row["decisions"] if d["selected"]]
        packed = pack_narrative_input(case, row["plan"], world,
                                      selected_fact_ids=selected)
        assert packed["status"] == "ok", case["id"]
        counts.append(len(tok(packed["input"]).input_ids))
    return min(counts), max(counts), len(counts)


def main():
    for name in UNITS:
        getattr(tests, name)()
    min_in, max_in, count = token_counts()
    payload = {
        "component": "N4.0",
        "name": "narrative input packing",
        "role": "program sub-step of the N4 generation model; structured records, no pre-written fact sentences",
        "version": N4_INPUT_VERSION,
        "date": "2026-11-02",
        "parentCommit": git_head(),
        "numbering": {
            "N4.0": "input packing (program)",
            "N4": "generation (model)",
            "N5": "verification",
        },
        "regression": {
            "cases": count,
            "allPackOk": True,
            "noLegacyFactSentences": True,
            "noTaskGoal": True,
            "noExactDuration": True,
            "deterministic": True,
        },
        "inputTokens": {"min": min_in, "max": max_in},
        "units": UNITS,
        "failClosedCodes": [
            "plan-shape-invalid", "facts-shape-invalid", "plan-refusal",
            "plan-unknown-fact", "duplicate-fact", "selected-unknown-fact",
            "plan-coverage-mismatch", "unsupported-fact-kind",
            "outcome-result-missing", "missing-field",
            "world-location-missing", "world-location-appearance-missing",
            "world-item-missing", "world-item-appearance-missing",
            "world-character-missing", "character-name-missing",
            "character-personality-missing", "character-appearance-missing",
            "scene-state-invalid", "scene-location-path-missing",
            "perspective-unresolved",
        ],
        "notes": [
            "N4.0 emits structured records; N4 writes every sentence.",
            "The legacy sentence-row renderer remains for frozen v2/v3 "
            "models and its 12+12 byte regression; it is not the new contract.",
            "No model call; packing is deterministic and program-only.",
            "N4 is not trained on this input yet.",
            "WorldState.Task has no resultText; the protocol source is "
            "FrozenGroupView.members[].resultText, not task status.",
        ],
        "sources": {rel: sha(rel) for rel in SOURCES},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"N4.0 evidence: {OUT}")
    print(f"tokens {min_in}-{max_in}; parent {payload['parentCommit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
