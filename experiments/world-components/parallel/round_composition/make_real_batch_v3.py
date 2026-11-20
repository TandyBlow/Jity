# Pre-register batch v3: the N4.0 REQUIREMENT-LINE intervention.
#
# Same 10 samples, same model digest, same 384-token budget, same frozen judge
# and the same retry policy as v2. The only change is the requirement line: the
# packed input's single 要求： line is replaced, verbatim, by the instruction set
# fixed below. The intervention is written BEFORE any v3 model call.
#
# Attribution, on the record: this is a whole-line intervention. Results can be
# attributed to the instruction set as a whole, not to individual clauses.
#
# Usage: python -X utf8 make_real_batch_v3.py

import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent.parent

CASES = HERE / "fixtures" / "batch-v1-cases.json"
V2_REG = HERE / "fixtures" / "batch-v2.json"
OUT = HERE / "fixtures" / "batch-v3.json"

ORIGINAL_LINE = ("要求：写场景、行动与视角人物心理；不写任务标题、数值面板、"
                 "具体时长、字段名；不新增未列出的具名人物/物品/地点；"
                 "他人只写可见动作。")

REPLACEMENT_LINE = (
    "要求：只输出一段完整正文，最多六句；写场景、行动与视角人物心理；"
    "不写任务标题、数值面板、具体时长、字段名；不回显记录行、编号或小节标签；"
    "不写对话；完整表达下列每一条事实，移动要交代起点和终点；"
    "不新增未列出的具名人物/物品/地点或事件；他人只写可见动作，不写他人内心。")


def sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    import requests
    v2 = json.loads(V2_REG.read_text(encoding="utf-8"))
    tags = requests.get("http://127.0.0.1:11434/api/tags", timeout=10).json()
    tag = next(m for m in tags["models"] if m["name"] == "qwen2.5:7b")
    if tag["digest"] != v2["model"]["digest"]:
        raise SystemExit("model digest changed since v2; refusing to register")
    version = requests.get("http://127.0.0.1:11434/api/version",
                           timeout=10).json()["version"]

    # every packed input must contain the registered original line exactly once,
    # otherwise the substitution would not be the registered intervention
    cases_doc = json.loads(CASES.read_text(encoding="utf-8"))
    for cid, dry in cases_doc["dryRun"].items():
        text = dry["input"]
        count = sum(1 for line in text.split(chr(10))
                    if line.startswith("要求："))
        if count != 1:
            raise SystemExit(f"{cid}: {count} requirement lines, expected 1")
        got = next(line for line in text.split(chr(10))
                   if line.startswith("要求："))
        if got != ORIGINAL_LINE:
            raise SystemExit(f"{cid}: requirement line differs from the "
                             f"registered original")

    orig_sha = hashlib.sha256(ORIGINAL_LINE.encode("utf-8")).hexdigest()
    repl_sha = hashlib.sha256(REPLACEMENT_LINE.encode("utf-8")).hexdigest()
    reg = {
        "version": "real-batch-v3",
        "batchId": "real-batch-2026-11-08-v3-shape",
        "registeredAt": "2026-11-08",
        "purpose": "N4.0 requirement-line intervention: v2 showed the model "
                   "writes complete passages but not the judged shapes. Only the "
                   "requirement line changes here.",
        "decisionRecord": {
            "intervention": "replace the N4.0 requirement line as a whole",
            "attribution": "whole-line intervention; results can only be "
                            "attributed to the instruction set, not to any "
                            "single clause",
            "judge": "frozen (judge_v3, n5-v3); no vocabulary or frame change",
            "budget": "384, unchanged from v2",
            "povAndInnerState": "stay N6 findings, no hard gate",
        },
        "sameSamplesAsV2": {
            "batchId": v2["batchId"],
            "casesSha256": sha(CASES),
        },
        "sampleIds": [c["caseId"] for c in cases_doc["cases"]],
        "sampleCount": len(cases_doc["cases"]),
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
            "temperature": 0, "seed": 42, "num_predict": 384,
            "top_p": 1.0, "top_k": 40, "repeat_penalty": 1.0, "stop": [],
            "stream": False, "system": None,
        },
        "intervention": {
            "kind": "requirement-line",
            "originalLine": ORIGINAL_LINE,
            "originalSha256": orig_sha,
            "replacementLine": REPLACEMENT_LINE,
            "replacementSha256": repl_sha,
            "transform": "replace the single line starting with 要求： in the "
                         "packed N4.0 input; exactly one such line must exist "
                         "and it must equal originalLine, otherwise the batch "
                         "stops",
            "scope": "all 10 samples; identical replacement text",
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
            "retry": "reported separately; never changes the primary number",
            "denominator": "all 10 samples, including truncated ones",
            "movementDenominator": "the 6 samples that carry a moved fact",
        },
        "acceptance": {
            "mechanism": [
                "10/10 samples record both the original and the intervened "
                "input, the raw response, finish reason, token counts, timing "
                "and the decision",
                "no unhandled exception; the intervention fails closed if the "
                "requirement line is not found exactly once",
            ],
            "quality": [
                "n5-pass means the hard gates passed ONLY",
                "quality comes from N6 (semantic, independent of the N5 regex)",
                "D4 counts proper names only (errata E5)",
                "review is bound to attempt 1 (reviewedAttempt=1); retry texts "
                "stay pending",
            ],
            "tripwire": [
                ">=3/10 samples failing the hard gates, OR >=2 failing port "
                "CALLS",
            ],
        },
        "n6Rubric": {
            "A_facts": "every selected fact is conveyed without contradiction",
            "B_additions": "no new named entity/event, no goal leak, no format "
                           "echo",
            "C_pov": "no other character's inner state and no POV switch",
            "D_completeness": "the passage ends as a complete sentence",
            "independence": "an N5 regex miss is NOT an N6 reason; N6 judges "
                            "what the text conveys",
            "verdict": "pass only when A-D hold; unreadable -> undetermined",
        },
        "registrationRevision": {
            "revision": 2,
            "reason": "the first v3 attempt sent the ORIGINAL requirement line "
                      "while archiving the intervened text (runner bug). The "
                      "aborted run is preserved and the runner was fixed before "
                      "any valid v3 result existed.",
            "abortedArchive": "out/real-batch-v3-aborted-no-intervention.json",
            "errata": "fixtures/errata-v3.json",
        },
        "errataInherited": {
            "v1": "fixtures/errata-v1.json (E1 tripwire, E2 wording, E3 tokens, "
                  "E4 time claim, E5 D4 rule)",
            "v2": "fixtures/errata-v2.json (N6 semantic independence, attempt "
                  "binding, movement denominator 6)",
        },
        "hashes": {
            "cases": sha(CASES),
            "judge": sha(HERE / "judge_v3.py"),
            "runner": sha(HERE / "real_batch_v3.py"),
            "v2Registration": sha(V2_REG),
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
    print(f"registered v3: {reg['sampleCount']} samples, requirement line "
          f"{reg['intervention']['replacementSha256'][:12]}, "
          f"num_predict={reg['decode']['num_predict']} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
