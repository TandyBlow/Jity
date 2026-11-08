"""Build the blind packet for the independent reviewer (no model calls).

The packet contains, per v3 sample: the authoritative record lines, the POV and
constraint lines, and the first-call text. It deliberately EXCLUDES the existing
N6 verdicts and D4 labels, so the second reviewer cannot be anchored.

It also builds a calibration set: six short texts with known ground truth, three
with an invented proper name and three clean, so "nothing detected" cannot be
mistaken for "able to detect". The key is written to a separate file.

Usage: python -X utf8 make_reviewer_packet.py
"""

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUN = HERE / "out" / "real-batch-v3.json"
PACKET = HERE / "fixtures" / "reviewer-packet-v3.json"
CALIB = HERE / "fixtures" / "reviewer-calibration.json"
KEY = HERE / "fixtures" / "reviewer-calibration-key.json"


def lines_of(render_text, prefix):
    return [l for l in render_text.split(chr(10)) if l.startswith(prefix)]


def main() -> int:
    run = json.loads(RUN.read_text(encoding="utf-8"))
    cases = []
    for c in run["cases"]:
        rt = c["renderText"]
        facts = [l for l in rt.split(chr(10))
                 if l[:1] == "f" and "｜" in l]
        persp = [l for l in rt.split(chr(10)) if l.startswith("视角：")]
        req = [l for l in rt.split(chr(10)) if l.startswith("要求：")]
        cases.append({
            "caseId": c["caseId"],
            "authoritativeFacts": facts,
            "perspective": persp[0] if persp else None,
            "writingRules": req[0] if req else None,
            "text": c["attempts"][0]["output"],
            "finishReason": c["attempts"][0]["finishReason"],
        })
    packet = {
        "version": "reviewer-packet-v3",
        "instructions": [
            "Read the authoritative facts, the perspective and the writing rules, "
            "then the text.",
            "For each fact say whether the text conveys it (yes / no / "
            "undetermined) and quote the evidence.",
            "Say whether two same-name actors are confused, whether the text "
            "adds an event or named entity that is not authorised, and whether "
            "the point of view changes.",
            "Rate readability 1-5. Do not score style preferences.",
            "Label the calibration texts too, without looking for a key.",
        ],
        "labelSchema": {
            "facts": [{"factId": "f0", "conveyed": "yes|no|undetermined",
                       "evidence": "verbatim quote"}],
            "sameNameConfused": "yes|no|undetermined",
            "unauthorizedAdditions": ["verbatim quote"],
            "povChanged": "yes|no|undetermined",
            "readability": "1-5",
        },
        "cases": cases,
    }
    PACKET.write_text(json.dumps(packet, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8", newline="\n")

    calib = {"version": "reviewer-calibration",
             "note": "label these six texts with the same schema; the key is a "
                     "separate file",
             "texts": [
                 {"id": "c1", "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼。他靠着栏杆喘了口气。"},
                 {"id": "c2", "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼。王五在楼梯口等他。"},
                 {"id": "c3", "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼。钟声在雾里散开。"},
                 {"id": "c4", "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼，又去了柳溪渡。"},
                 {"id": "c5", "text": "管线甲从管线镇来到了钟楼。管线甲并未把铜铃挂回钟楼。"},
                 {"id": "c6", "text": "管线甲从管线镇来到了钟楼，把铜铃挂回了钟楼。他的手指还在抖。"},
             ]}
    key = {"c1": {"inventedName": False, "factConveyed": True},
           "c2": {"inventedName": True, "inventedWho": "王五"},
           "c3": {"inventedName": False, "factConveyed": True},
           "c4": {"inventedName": True, "inventedWho": "柳溪渡（地点）"},
           "c5": {"inventedName": False, "factConveyed": False,
                  "why": "negated result"},
           "c6": {"inventedName": False, "factConveyed": True}}
    CALIB.write_text(json.dumps(calib, ensure_ascii=False, indent=1) + "\n",
                     encoding="utf-8", newline="\n")
    KEY.write_text(json.dumps(key, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"packet: {len(cases)} cases -> {PACKET.name}")
    print(f"calibration: 6 texts -> {CALIB.name} (key: {KEY.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
