# D4 labels and N6 verdicts for batch v3 (requirement-line intervention).
#
# Bound to the FIRST call (reviewedAttempt=1); retry texts are archived but not
# reviewed. N6 judges semantics independently of the N5 regex: a formal miss is
# listed under n5Formal and never used as an N6 reason. D4 counts proper names
# only (errata E5). Movement is reported over the 6 samples that carry a moved
# fact.
#
# Usage: python -X utf8 write_review_v3.py

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUN = HERE / "out" / "real-batch-v3.json"
OUT = HERE / "fixtures" / "review-v3.json"

run = json.loads(RUN.read_text(encoding="utf-8"))
cases = {c["caseId"]: c for c in run["cases"]}


def first_text(cid):
    return cases[cid]["attempts"][0]["output"]


def formal(cid):
    return (cases[cid]["attempts"][0].get("n5") or {}).get("problems") or []


def n6(rubric, reasons, observations=None):
    out = {"status": "executed", "result": "fail", "rubric": rubric,
           "reasons": reasons}
    if observations:
        out["observations"] = observations
    return out


REVIEW = {
    "version": "real-batch-v3-review",
    "batchId": run["batchId"],
    "reviewedAt": "2026-11-08",
    "reviewer": "assistant-manual (single reviewer, same session that ran the "
                "batch)",
    "reviewStatus": "pending-independent-review",
    "reviewedAttempt": 1,
    "scope": "first call text per sample; retry texts are archived but not "
             "reviewed (pending); template fallbacks are program output",
    "separationRule": "N5 formal findings are listed under n5Formal; N6 reasons "
                      "are semantic judgements only.",
    "d4Rule": "proper names only, absent from the registry AND from the "
              "authoritative text; object/place descriptions are N6 notes",
    "n6Rule": "A facts conveyed without contradiction; B no invented named "
              "entity/event, no goal leak, no format echo or meta-talk; C no "
              "other character's inner state and no POV switch; D complete "
              "sentence. pass only when A-D hold.",
    "caseMeta": {
        "rb-move-outcome": {"hasMovedFact": True},
        "rb-time-vague": {"hasMovedFact": True},
        "rb-inner-change": {"hasMovedFact": False},
        "rb-two-actors-move": {"hasMovedFact": True},
        "rb-same-name": {"hasMovedFact": True},
        "rb-subtask": {"hasMovedFact": True},
        "rb-sanity-only": {"hasMovedFact": False},
        "rb-time-only": {"hasMovedFact": False},
        "rb-conflict-two-actors": {"hasMovedFact": False},
        "rb-move-other-appearance": {"hasMovedFact": True},
    },
    "cases": {
        "rb-move-outcome": {
            "text": first_text("rb-move-outcome"),
            "n5Formal": formal("rb-move-outcome"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the move is not conveyed: the text opens inside 钟楼 and "
                      "never mentions 管线镇",
                      "invents a stairs climb and a quiet exit"],
                     ["the result is conveyed ('将铜铃挂回原位')",
                      "one paragraph, no dialogue, no field echo (the "
                      "instruction was followed on shape)"]),
        },
        "rb-time-vague": {
            "text": first_text("rb-time-vague"),
            "n5Formal": formal("rb-time-vague"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the move is not conveyed",
                      "invents a search and a relieved sigh"],
                     ["the result is conveyed ('轻轻挂回原位')",
                      "the elapsed time is conveyed ('过去了一会儿')"]),
        },
        "rb-inner-change": {
            "text": first_text("rb-inner-change"),
            "n5Formal": formal("rb-inner-change"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the personality change is not conveyed",
                      "the sanity change is ambiguous: '渐渐平静下来' could be "
                      "read either way, so it is not a conveyed fact",
                      "invents street lights, a crowd and a night mood"],
                     ["the appearance change is conveyed (rain soaking the "
                      "coat)"]),
        },
        "rb-two-actors-move": {
            "text": first_text("rb-two-actors-move"),
            "n5Formal": formal("rb-two-actors-move"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": False, "D": True},
                     ["neither actor's move is conveyed",
                      "attributes hiding intent to 管线乙 ('似乎生怕被什么人"
                      "发现')",
                      "invents a corridor and a following scene"]),
        },
        "rb-same-name": {
            "text": first_text("rb-same-name"),
            "n5Formal": formal("rb-same-name"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the move is only partially conveyed: '他从管线镇出发' "
                      "gives the origin and 钟楼 comes into view, but arrival is "
                      "never stated",
                      "the two 管线乙 are shown following him, so their own "
                      "moves are not conveyed",
                      "invents panting and a silent-follower scene"],
                     ["G4 triggered and satisfied: both 管线乙 are named"]),
        },
        "rb-subtask": {
            "text": first_text("rb-subtask"),
            "n5Formal": formal("rb-subtask"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the new subtask (being given 找梯子) is not conveyed; the "
                      "text searches for a ladder on its own initiative",
                      "the move is not conveyed",
                      "invents a climb and a bell at the top"]),
        },
        "rb-sanity-only": {
            "text": first_text("rb-sanity-only"),
            "n5Formal": formal("rb-sanity-only"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the personality change is not conveyed",
                      "invents residents, an unknown danger and an inner "
                      "struggle"],
                     ["the sanity change is conveyed as a decline ('理智却在逐渐"
                      "模糊')"]),
        },
        "rb-time-only": {
            "text": first_text("rb-time-only"),
            "n5Formal": formal("rb-time-only"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the no-change fact is not conveyed: the text walks to an "
                      "abandoned factory area",
                      "invents 井盖 and 旧工厂区 (place description, N6 note)",
                      "the elapsed time is conveyed ('过去了一会儿')"]),
        },
        "rb-conflict-two-actors": {
            "text": first_text("rb-conflict-two-actors"),
            "n5Formal": formal("rb-conflict-two-actors"),
            "d4": {"annotations": []},
            "n6": n6({"A": True, "B": False, "C": False, "D": True},
                     ["switches to first person ('我', '我们'), which the "
                      "instruction forbids and the record's POV excludes",
                      "attributes 急躁 to 管线乙 and narrates his effort",
                      "invents a destination (镇中心的新广场) and a carrying "
                      "plan"],
                     ["both result texts are conveyed semantically: the bell "
                      "is lifted off the ground and 管线乙 braces against the "
                      "rim",
                      "no section-label echo this time, unlike v2"]),
        },
        "rb-move-other-appearance": {
            "text": first_text("rb-move-other-appearance"),
            "n5Formal": formal("rb-move-other-appearance"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the move is only named, not conveyed: '完成了任务指令中"
                      "的移动' is meta-talk about the instruction, with no "
                      "origin or destination",
                      "the other actor's appearance change is absent (correct, "
                      "it was not selected)",
                      "invents a stairs climb and dust"]),
        },
    },
    "summary": {
        "reviewed": 10,
        "reviewedAttempt": 1,
        "n6Executed": 10,
        "n6Pass": 0,
        "n6Fail": 10,
        "n6Undetermined": 0,
        "d4Labeled": 10,
        "d4ProperNames": 0,
        "d4ProperNameList": [],
        "d4DescriptionsMovedToN6": ["镇中心的新广场", "旧工厂区", "井盖"],
        "movedFactSamples": 6,
        "movedFactSampleIds": ["rb-move-outcome", "rb-time-vague",
                               "rb-two-actors-move", "rb-same-name",
                               "rb-subtask", "rb-move-other-appearance"],
        "movedConveyed": 0,
        "movedPartial": ["rb-same-name"],
        "factsConveyedSemantically": {
            "rb-move-outcome": ["outcome"],
            "rb-time-vague": ["outcome", "time"],
            "rb-inner-change": ["appearance_changed"],
            "rb-sanity-only": ["sanity_changed"],
            "rb-time-only": ["time"],
            "rb-conflict-two-actors": ["outcome", "outcome"],
        },
        "commonFindings": [
            "0/10 truncated: every first call ended normally (77-121 output "
            "tokens, versus 215-384 in v2)",
            "shape instruction was followed on length and format: one paragraph, "
            "no section-label echo, no record-line echo, no dialogue",
            "but the moved fact is conveyed in 0 of the 6 samples that carry one; "
            "one sample gives only its origin",
            "the model still writes another character's inner state in 2 samples "
            "and switches to first person in 1",
            "hard gates remain 0/10 because the frames require the fact wording "
            "(从 A 来到 B / the authoritative result text), which the model "
            "paraphrases",
        ],
        "limit": "single reviewer; verdicts pending independent review",
    },
}

OUT.write_text(json.dumps(REVIEW, ensure_ascii=False, indent=1) + "\n",
               encoding="utf-8", newline="\n")
print(f"review -> {OUT}")
