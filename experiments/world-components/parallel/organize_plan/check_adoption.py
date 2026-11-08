# -*- coding: utf-8 -*-
"""Strict adoption rules for a plan-trained checkpoint.

Design rule from the review: a hash that merely appears as text inside a file is
not attribution. The record must link the weight hash to

    * the training inputs and the plan format the model consumed,
    * the training run itself (recipe + a record that stores the hash in a field),
    * the selection result (which epoch/update was chosen and with what metric),

and it must not be satisfied by the base-model hash: the base model was never
trained on plan blocks, so "the hash matches something" is exactly the failure
mode this file exists to prevent.

Adoption record (`freeze/checkpoint-adoption.json`):

{
  "weightFile": "D:/.../ckpt/model.safetensors",
  "modelSha256": "…",
  "baseModel": {"modelSha256": "5cdc5721…", "note": "77M base, unchanged"},
  "trainingInputs": {
     "materialFile": "artifacts/.../controllability-v1.jsonl",
     "materialSha256": "…",
     "planFormat": "groups/refs/edges v1 (factIds + continuation/parallel + name/omit + before edges)",
     "planCount": 72,
     "sourceCount": 36
  },
  "trainingRun": {
     "record": "artifacts/.../run.json",
     "recordSha256": "…",
     "recordField": "model.files.model.safetensors",
     "recipe": {"base": "…", "updates": 120, "lr": 0.0005, "seed": 13},
     "producedAt": "…",
     "producerCommit": "…"
  },
  "selection": {
     "record": "artifacts/.../run.json",
     "recordSha256": "…",
     "recordField": "selection.selectedSha256",
     "epoch": 9, "updates": 90, "metric": "dev paired success", "metricValue": 0
  },
  "decode": {"strategy": "greedy", "maxNewTokens": 128},
  "device": "cpu|cuda|browser",
  "trainedOnPlanBlocks": true
}

Usage:
    python -X utf8 check_adoption.py --explain
    python -X utf8 check_adoption.py            # validate freeze/checkpoint-adoption.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADOPTION = HERE / "freeze" / "checkpoint-adoption.json"

# The only weight the local records actually pin; it must never satisfy adoption.
BASE_77M_SHA256 = "5cdc572109cf25914b43fede20a6949b5fbf50b3a091a9c445fac60059bf5557"

REQUIRED = {
    "weightFile": "path to the .safetensors/.bin to be used",
    "modelSha256": "sha256 of that file",
    "baseModel.modelSha256": "sha256 of the base the run started from",
    "trainingInputs.materialFile": "the material the run trained on",
    "trainingInputs.materialSha256": "sha256 of that material",
    "trainingInputs.planFormat": "what plan fields the model consumed",
    "trainingInputs.planCount": "how many plan items were used",
    "trainingRun.record": "a json record from the training run",
    "trainingRun.recordSha256": "sha256 of that record",
    "trainingRun.recordField": "dotted path inside the record whose VALUE equals modelSha256",
    "trainingRun.recipe": "optimizer-visible settings (updates/lr/seed/...)",
    "selection.record": "a json record with the selection result",
    "selection.recordSha256": "sha256 of that record",
    "selection.recordField": "dotted path inside the record whose VALUE is a hash of the same weights",
    "selection.epoch": "selected epoch",
    "selection.updates": "selected optimizer updates",
    "selection.metric": "the metric used to select",
    "decode.strategy": "decoding settings actually used",
    "device": "where inference will run",
    "trainedOnPlanBlocks": "must be true",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def get_path(obj, path: str):
    """Resolve `path` against `obj`.

    Keys in these records contain dots ("model.safetensors"), so a plain split
    is wrong. Behaviour:
      * "/a/b/c" is a JSON Pointer;
      * otherwise each step takes the LONGEST literal key that matches, which
        makes "model.files.model.safetensors" work with a dotted key.
    """
    if path.startswith("/"):
        cur = obj
        for raw in path.strip("/").split("/"):
            part = raw.replace("~1", "/").replace("~0", "~")
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list):
                try:
                    cur = cur[int(part)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        return cur

    parts = path.split(".")
    cur, i = obj, 0
    while i < len(parts):
        if isinstance(cur, dict):
            for j in range(len(parts), i, -1):
                key = ".".join(parts[i:j])
                if key in cur:
                    cur = cur[key]
                    i = j
                    break
            else:
                return None
        elif isinstance(cur, list):
            try:
                cur = cur[int(parts[i])]
            except (ValueError, IndexError):
                return None
            i += 1
        else:
            return None
    return cur


def check(record: Path | None = None) -> list[str]:
    path = record or ADOPTION
    if not path.exists():
        return [f"{path} does not exist"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    problems: list[str] = []

    def need(dotted: str) -> None:
        if get_path(doc, dotted) in (None, "", [], {}):
            problems.append(f"missing {dotted}")

    for dotted in REQUIRED:
        need(dotted)

    if get_path(doc, "trainedOnPlanBlocks") is not True:
        problems.append("trainedOnPlanBlocks is not true")

    weight = Path(get_path(doc, "weightFile") or "")
    model_sha = get_path(doc, "modelSha256")
    base_sha = get_path(doc, "baseModel.modelSha256")
    if model_sha and base_sha and model_sha == base_sha:
        problems.append("modelSha256 equals baseModel.modelSha256: the base model was never trained "
                        "on plan blocks, so this cannot be an adopted checkpoint")
    if model_sha == BASE_77M_SHA256:
        problems.append("modelSha256 is the known 77M base hash: matching the base weight is not "
                        "attribution")
    if weight and weight.exists():
        if model_sha and sha256(weight) != model_sha:
            problems.append("weight file sha256 does not match modelSha256")
    elif weight:
        problems.append(f"weight file does not exist: {weight}")

    # trainingInputs: the material must exist and match, and the plan format
    # must be stated explicitly (a base model has no plan format at all).
    mat = Path(get_path(doc, "trainingInputs.materialFile") or "")
    if mat and mat.exists():
        want = get_path(doc, "trainingInputs.materialSha256")
        if want and sha256(mat) != want:
            problems.append("trainingInputs.materialSha256 does not match the material file")
    elif mat:
        problems.append(f"trainingInputs.materialFile does not exist: {mat}")

    # trainingRun / selection: the hash must be a VALUE at the stated path, not
    # a substring somewhere in the file.
    for block, label in (("trainingRun", "trainingRun"), ("selection", "selection")):
        rec_rel = get_path(doc, f"{block}.record")
        rec_sha = get_path(doc, f"{block}.recordSha256")
        field = get_path(doc, f"{block}.recordField")
        if not rec_rel:
            continue
        rec_path = HERE / rec_rel
        if not rec_path.exists():
            problems.append(f"{label}.record does not exist: {rec_rel}")
            continue
        if rec_sha and sha256(rec_path) != rec_sha:
            problems.append(f"{label}.recordSha256 does not match {rec_rel}")
        try:
            rec = json.loads(rec_path.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"{label}.record is not readable JSON: {exc}")
            continue
        if field:
            value = get_path(rec, field)
            if value is None:
                problems.append(f"{label}.recordField {field!r} does not exist in {rec_rel}")
            elif not model_sha or value != model_sha:
                problems.append(f"{label}.recordField {field!r} = {str(value)[:16]}… does not equal "
                                f"modelSha256: a hash found only as text elsewhere is not attribution")

    # trainingRun and selection should describe the same run
    if get_path(doc, "trainingRun.record") and get_path(doc, "selection.record"):
        if get_path(doc, "trainingRun.recordSha256") != get_path(doc, "selection.recordSha256"):
            problems.append("trainingRun and selection point at different records; the selection must "
                            "come from the same run that produced the weights")

    return problems


def explain() -> int:
    print("checkpoint adoption record: required fields\n")
    width = max(len(k) for k in REQUIRED)
    for key, desc in REQUIRED.items():
        print(f"  {key:<{width}}  {desc}")
    print(f"\nbase hash that must never satisfy adoption: {BASE_77M_SHA256}")
    print("\nattribution rule: trainingRun.recordField and selection.recordField must resolve to a value")
    print("equal to modelSha256. A hash that merely appears somewhere in a file does not count.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--explain", action="store_true")
    ap.add_argument("--record", help="validate this record instead of freeze/checkpoint-adoption.json")
    args = ap.parse_args()
    if args.explain:
        return explain()
    problems = check(Path(args.record) if args.record else None)
    if problems:
        print(json.dumps({"status": "not-adopted", "problems": problems}, ensure_ascii=False, indent=1))
        return 1
    print(json.dumps({"status": "adopted"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
