# Pre-register batch v2: the 384-token output-budget comparison.
#
# Same 10 samples as v1 (same cases file, same hash), same model digest, same
# prompt, same frozen judge, same retry policy. Only `num_predict` changes:
# 128 -> 384. The primary result is the FIRST call; the retry is reported
# separately. Truncated samples stay in the denominator.
#
# Written BEFORE any v2 model call. Usage: python -X utf8 make_real_batch_v2.py

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent

CASES = HERE / "fixtures" / "batch-v1-cases.json"
V1_REG = HERE / "fixtures" / "batch-v1.json"
OUT = HERE / "fixtures" / "batch-v2.json"


def sha(path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    import requests
    v1 = json.loads(V1_REG.read_text(encoding="utf-8"))
    tags = requests.get("http://127.0.0.1:11434/api/tags", timeout=10).json()
    tag = next(m for m in tags["models"] if m["name"] == "qwen2.5:7b")
    if tag["digest"] != v1["model"]["digest"]:
        raise SystemExit("model digest changed since v1; refusing to register")
    version = requests.get("http://127.0.0.1:11434/api/version",
                           timeout=10).json()["version"]
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]

    reg = {
        "version": "real-batch-v2",
        "batchId": "real-batch-2026-11-08-v2-budget384",
        "registeredAt": "2026-11-08",
        "purpose": "output-budget control for the C7 real-model batch: the v1 "
                   "configuration truncated every passage at num_predict=128. "
                   "Only that number changes here; samples, model, prompts, "
                   "judge and retry policy are identical.",
        "decisionRecord": {
            "outputBudget": "384 approved by the owner",
            "outputShapeInstruction": "NOT changed in this batch (held for a "
                                      "separate controlled comparison)",
            "povAndInnerState": "remain N6 findings, no hard gate",
            "judge": "frozen; no vocabulary or frame changes after seeing v1",
        },
        "sameSamplesAsV1": {
            "batchId": v1["batchId"],
            "casesSha256": sha(CASES),
            "note": "byte-identical cases file; the dry-run facts/selection/"
                    "plan are in that file",
        },
        "sampleIds": [c["caseId"] for c in cases],
        "sampleCount": len(cases),
        "model": {
            "name": tag["name"], "digest": tag["digest"],
            "parameterSize": tag["details"].get("parameter_size"),
            "quantization": tag["details"].get("quantization_level"),
            "family": tag["details"].get("family"),
            "runtime": "ollama", "runtimeVersion": version,
            "endpoint": "http://127.0.0.1:11434/api/generate",
            "transport": "local HTTP, no external network",
        },
        "decode": {
            "temperature": 0, "seed": 42,
            "num_predict": 384,
            "top_p": 1.0, "top_k": 40, "repeat_penalty": 1.0, "stop": [],
            "stream": False, "system": None,
            "templateNote": "identical prompt handling to v1",
        },
        "retryPolicy": {
            "maxSentenceAttempts": 2,
            "feedback": "the previous attempt's hard-gate problems are "
                        "appended to the retry request (recorded)",
            "fallback": "program template when the kinds have a frame; the "
                        "case status stays a failure",
        },
        "primaryMetric": {
            "value": "first call only (attempt 1)",
            "retry": "reported separately; a retry can never change the "
                     "primary number",
            "denominator": "all 10 samples, including truncated ones",
        },
        "acceptance": {
            "mechanism": [
                "10/10 samples produce a complete record: prompt, raw "
                "response, finish reason, token counts, timing, decision",
                "no unhandled exception; every call has an explicit status",
            ],
            "quality": [
                "n5-pass means the hard gates passed ONLY",
                "quality comes from N6 (pass / fail / undetermined), reviewed "
                "per sample against the committed facts",
                "D4 counts proper names only, absent from the state registry "
                "AND from the authoritative text; object/place descriptions "
                "are N6 notes, not D4 labels (errata E5)",
            ],
            "tripwire": [
                "fires when >=3/10 samples fail the hard gates "
                "(hardGateFailSamples >= 3), OR when >=2 CALLS fail at the "
                "port level (portFailureCalls >= 2)",
                "port failures are counted per call, not per sample "
                "(errata E1)",
            ],
        },
        "n6Rubric": {
            "A_facts": "every selected fact is stated without contradiction",
            "B_additions": "no new named entity/place/item, no invented event, "
                           "no task-goal leak",
            "C_pov": "no other character's inner state narrated",
            "D_completeness": "the passage ends as a complete sentence",
            "verdict": "pass only when A-D all hold; unreadable -> "
                       "undetermined; anything else -> fail",
        },
        "errataInherited": {
            "source": "fixtures/errata-v1.json",
            "applied": ["E1 tripwire text and counting", "E5 D4 proper-name "
                        "rule"],
        },
        "hashes": {
            "cases": sha(CASES),
            "judge": sha(HERE / "judge_v3.py"),
            "runner": sha(HERE / "real_batch_v2.py"),
            "v1Registration": sha(V1_REG),
            "chain": {
                "narration_pipeline.py": sha(WC / "narration_pipeline.py"),
                "n2_perspective.py": sha(WC / "n2_perspective.py"),
                "n3_organize.py": sha(WC / "n3_organize.py"),
                "packer.py": sha(WC / "n4_input_renderer" / "packer.py"),
                "scene_context.py": sha(WC / "n4_input_renderer" /
                                        "scene_context.py"),
            },
        },
    }
    OUT.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"registered v2: {reg['sampleCount']} samples, "
          f"num_predict={reg['decode']['num_predict']}, "
          f"model={reg['model']['name']} {reg['model']['digest'][:12]} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
