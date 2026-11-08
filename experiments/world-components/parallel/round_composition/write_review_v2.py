# D4 labels and N6 verdicts for batch v2 (384-token budget), SECOND revision.
#
# Revision reasons (owner review, 2026-11-08):
#   - N6 must judge semantics on its own. A regex/N5 miss is NOT an N6 reason:
#     "将铜铃挂回原位" does convey the result, so it cannot be counted as a
#     semantic fact miss. Formal (N5) findings are listed separately under
#     `n5Formal` and never copied into `reasons`.
#   - The review is bound to the FIRST call (`reviewedAttempt: 1`). Retry texts
#     are archived but not reviewed, so their quality stays pending.
#   - The movement denominator is the 6 samples that carry a moved fact, not all
#     10; the summary reports that denominator explicitly.
#
# D4 follows errata E5: proper names only, absent from the registry AND from the
# authoritative text.
#
# Usage: python -X utf8 write_review_v2.py

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUN = HERE / "out" / "real-batch-v2.json"
OUT = HERE / "fixtures" / "review-v2.json"

run = json.loads(RUN.read_text(encoding="utf-8"))
cases = {c["caseId"]: c for c in run["cases"]}


def first_text(cid):
    return cases[cid]["attempts"][0]["output"]


def first_formal(cid):
    problems = (cases[cid]["attempts"][0].get("n5") or {}).get("problems") or []
    return problems


def n6(rubric, reasons, observations=None):
    out = {"status": "executed", "result": "fail", "rubric": rubric,
           "reasons": reasons}
    if observations:
        out["observations"] = observations
    return out


REVIEW = {
    "version": "real-batch-v2-review-r2",
    "batchId": run["batchId"],
    "reviewedAt": "2026-11-08",
    "reviewer": "assistant-manual (single reviewer, same session that ran the "
                "batch)",
    "reviewStatus": "pending-independent-review",
    "reviewedAttempt": 1,
    "scope": "the FIRST call text of each sample; retry texts are archived but "
             "NOT reviewed (their quality stays pending); template fallbacks "
             "are program output and are never reviewed as model text",
    "separationRule": "N5 (formal) and N6 (semantic) are judged independently. "
                      "A regex miss is recorded under n5Formal only; an N6 "
                      "reason must be a semantic judgement about what the text "
                      "conveys.",
    "d4Rule": "proper names only (person/item/place), absent from the state "
              "registry AND from the authoritative text; object/place "
              "descriptions go to N6 notes (errata E5)",
    "n6Rule": "A facts conveyed without contradiction; B no invented named "
              "entity/event/goal leak/format echo; C no other character's inner "
              "state and no POV switch; D the passage ends as a complete "
              "sentence. pass only when A-D hold.",
    "caseMeta": {
        # moved-fact denominator: only these 6 samples carry a moved fact
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
            "n5Formal": first_formal("rb-move-outcome"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the text opens inside 钟楼 and never conveys the "
                      "origin 管线镇, so the move as a whole (A→B) is not "
                      "conveyed",
                      "invents a backstory (铜铃曾是钟楼的灵魂, 守护小镇的愿望) "
                      "and a farewell scene"],
                     ["the result is conveyed: '将铜铃挂回原位' says the bell "
                      "was hung back, even though the wording differs from the "
                      "record",
                      "the formal miss of the result frame is recorded under "
                      "n5Formal only"]),
        },
        "rb-time-vague": {
            "text": first_text("rb-time-vague"),
            "n5Formal": first_formal("rb-time-vague"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the move is not conveyed (the text is already inside)",
                      "no elapsed time is conveyed: '夕阳的余晖' marks time of "
                      "day, not the passage of the eight minutes",
                      "invents an ending (守护小镇的愿望)"],
                     ["the result is conveyed ('将铜铃挂回原位')"]),
        },
        "rb-inner-change": {
            "text": first_text("rb-inner-change"),
            "n5Formal": first_formal("rb-inner-change"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the sanity change is not conveyed: '理智在这一刻显得尤为"
                      "重要' is a comment, not a change",
                      "invents an unexplained tension and a quest framing"],
                     ["the appearance change is conveyed semantically (rain "
                      "soaking the coat), although not in the record's words",
                      "the personality change is conveyed ('他的话少了许多')"]),
        },
        "rb-two-actors-move": {
            "text": first_text("rb-two-actors-move"),
            "n5Formal": first_formal("rb-two-actors-move"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": False, "D": False},
                     ["truncated at 384 tokens",
                      "neither actor's move is conveyed",
                      "invents dialogue ('快，我们得赶紧，时间不多了！') and "
                      "attributes urgency and intent to 管线乙"]),
        },
        "rb-same-name": {
            "text": first_text("rb-same-name"),
            "n5Formal": first_formal("rb-same-name"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the two 管线乙 are described standing downstairs; no "
                      "arrival is conveyed for any of the three actors",
                      "invents a pipeline inspection and approaching footsteps"],
                     ["G4 was triggered by data and satisfied: both 管线乙 are "
                      "mentioned separately"]),
        },
        "rb-subtask": {
            "text": first_text("rb-subtask"),
            "n5Formal": first_formal("rb-subtask"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the new subtask (being given 找梯子) is not conveyed; "
                      "the text instead performs a search and assembly",
                      "the move is not conveyed",
                      "invents cleaning, assembling and fixing the ladder"]),
        },
        "rb-sanity-only": {
            "text": first_text("rb-sanity-only"),
            "n5Formal": first_formal("rb-sanity-only"),
            "d4": {"annotations": [
                {"snippet": "老李", "position": "第7-9段", "source": "human",
                 "reviewStatus": "pending-independent-review", "isError": True,
                 "note": "a new person name absent from the registry and from "
                         "the authoritative text"},
            ]},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["neither the sanity drop nor the personality change is "
                      "conveyed as a change",
                      "invents a neighbour 老李 and a dialogue with him"],
                     ["the only genuine D4 proper name in this batch"]),
        },
        "rb-time-only": {
            "text": first_text("rb-time-only"),
            "n5Formal": first_formal("rb-time-only"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": False},
                     ["truncated at 384 tokens",
                      "'一切如旧' is not conveyed: the text shows an inspection "
                      "finding a possible blockage",
                      "invents a task, a detector and a blockage"]),
        },
        "rb-conflict-two-actors": {
            "text": first_text("rb-conflict-two-actors"),
            "n5Formal": first_formal("rb-conflict-two-actors"),
            "d4": {"annotations": []},
            "n6": n6({"A": True, "B": False, "C": True, "D": True},
                     ["echoes the input section labels ('场景：', '行动与心理：', "
                      "'可见动作：') into the prose",
                      "invents inner speech and dialogue"],
                     ["both result texts are conveyed semantically: the bell is "
                      "lifted off the ground and 管线乙 braces its shoulder "
                      "against the rim",
                      "the formal misses are recorded under n5Formal only"]),
        },
        "rb-move-other-appearance": {
            "text": first_text("rb-move-other-appearance"),
            "n5Formal": first_formal("rb-move-other-appearance"),
            "d4": {"annotations": []},
            "n6": n6({"A": False, "B": False, "C": True, "D": True},
                     ["the move is not conveyed; the text starts inside",
                      "copies and then rewrites the record line: 'f0｜移动｜钟面"
                      "→钟楼边缘' and 'f0｜移动｜钟楼边缘→钟楼内部' contradict the "
                      "fact (管线镇→钟楼)"],
                     ["worst format failure of the batch: the model treats the "
                      "record line as editable content"]),
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
        "d4ProperNames": 1,
        "d4ProperNameList": ["老李"],
        "movedFactSamples": 6,
        "movedFactSampleIds": ["rb-move-outcome", "rb-time-vague",
                               "rb-two-actors-move", "rb-same-name",
                               "rb-subtask", "rb-move-other-appearance"],
        "movedNotConveyed": 6,
        "factsConveyedSemantically": {
            "rb-move-outcome": ["outcome"],
            "rb-time-vague": ["outcome"],
            "rb-inner-change": ["appearance_changed", "personality_changed"],
            "rb-conflict-two-actors": ["outcome", "outcome"],
        },
        "commonFindings": [
            "8/10 first calls ended normally (done_reason=stop); 2 hit the 384 "
            "cap",
            "all 6 samples that carry a moved fact fail to convey the move; "
            "the denominator is 6, not 10",
            "several facts ARE conveyed semantically and fail only the formal "
            "frame: 将铜铃挂回原位 conveys the result, the soaked coat conveys "
            "the appearance change, 肩膀抵住了钟沿 conveys the second result",
            "3 samples echo section labels or record lines; one also rewrites "
            "the record's from/to values",
            "the only genuine D4 proper name is 老李",
        ],
        "limit": "single reviewer; false negatives are not measurable here; "
                 "verdicts are pending independent review",
    },
}

OUT.write_text(json.dumps(REVIEW, ensure_ascii=False, indent=1) + "\n",
               encoding="utf-8", newline="\n")
print(f"review -> {OUT}")
