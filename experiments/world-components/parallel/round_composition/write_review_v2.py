# D4 labels and N6 verdicts for batch v2 (384-token budget).
#
# Reviewed artefact, written after the run. The reviewed text is each sample's
# FIRST call (the primary metric the owner asked for); retry texts are not
# re-reviewed here — they are in the run archive if a later pass wants them.
#
# D4 uses the tightened rule inherited from errata E5: count PROPER NAMES only
# (person/item/place names) that are absent from the state registry AND from the
# authoritative text given to the model. Object/place descriptions are N6 notes,
# not D4 labels.
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


REVIEW = {
    "version": "real-batch-v2-review",
    "batchId": run["batchId"],
    "reviewedAt": "2026-11-08",
    "reviewer": "assistant-manual (single reviewer, same session that ran the "
                "batch)",
    "reviewStatus": "pending-independent-review",
    "scope": "the FIRST call text of each sample (primary metric); retry texts "
             "are archived but not re-reviewed here; template fallbacks are "
             "program output and are never reviewed as model text",
    "d4Rule": "proper names only (person/item/place), absent from the state "
              "registry AND from the authoritative text. Object/place "
              "descriptions (钟架/木梯/小巷/老邻居…) go to N6 notes, not D4 "
              "(errata E5).",
    "n6Rule": "A facts stated without contradiction; B no invented named "
              "entity/event/goal leak/format echo; C no other character's inner "
              "state and no POV switch; D the passage ends as a complete "
              "sentence. pass only when A-D hold; unreadable -> undetermined.",
    "cases": {
        "rb-move-outcome": {
            "text": first_text("rb-move-outcome"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": True},
                   "reasons": [
                       "the move 管线镇→钟楼 is never stated; the text starts "
                       "inside 钟楼",
                       "the result text 把铜铃挂回了钟楼 is paraphrased "
                       "('将铜铃挂回原位'), so the fact is not checkable",
                       "adds an invented backstory (铜铃曾是钟楼的灵魂) and a "
                       "farewell scene",
                   ],
                   "observations": [
                       "passage complete (done_reason=stop, 246 tokens)",
                       "frame mismatch, not truncation, is the binding "
                       "constraint here",
                   ]},
        },
        "rb-time-vague": {
            "text": first_text("rb-time-vague"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": True},
                   "reasons": [
                       "the move and the result are never stated",
                       "time is written only as scenery ('夕阳的余晖'), not as "
                       "an elapsed duration or a vague '过了一会儿'",
                       "adds invented content (守护小镇的愿望)",
                   ]},
        },
        "rb-inner-change": {
            "text": first_text("rb-inner-change"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": True},
                   "reasons": [
                       "the appearance change is shown as rain soaking the coat "
                       "but never as the recorded change text",
                       "the personality text 话少了许多 appears, but without "
                       "the frame, so it is not checkable",
                       "sanity is described only as '理智在这一刻显得尤为"
                       "重要', not as a change",
                   ]},
        },
        "rb-two-actors-move": {
            "text": first_text("rb-two-actors-move"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": False, "D": False},
                   "reasons": [
                       "truncated at 384 tokens ('钟' at the end)",
                       "neither actor's move is stated",
                       "invents dialogue ('快，我们得赶紧，时间不多了！') and "
                       "attributes urgency and intent to 管线乙",
                   ]},
        },
        "rb-same-name": {
            "text": first_text("rb-same-name"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": True},
                   "reasons": [
                       "the three moves are never stated; the two 管线乙 are "
                       "described as standing downstairs, not arriving",
                       "adds invented events (检查管线系统/脚步声/两个身影)",
                   ],
                   "observations": [
                       "G4 triggered and was satisfied: both 管线乙 are "
                       "mentioned separately",
                       "this is the first sample where the same-name discipline "
                       "is met",
                   ]},
        },
        "rb-subtask": {
            "text": first_text("rb-subtask"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": True},
                   "reasons": [
                       "the move and the new subtask are never stated; the "
                       "ladder is found and used, which is a different event",
                       "adds invented actions (cleaning, assembling, fixing the "
                       "ladder)",
                   ]},
        },
        "rb-sanity-only": {
            "text": first_text("rb-sanity-only"),
            "d4": {"annotations": [
                {"snippet": "老李", "position": "第7-9段", "source": "human",
                 "reviewStatus": "pending-independent-review", "isError": True,
                 "note": "a new person name that is in no registry or "
                         "authoritative text"},
            ]},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": True},
                   "reasons": [
                       "neither the sanity drop nor the personality change is "
                       "stated as a change",
                       "invents a neighbour 老李 and a dialogue with him",
                   ],
                   "observations": ["the only genuine D4 proper name in this "
                                    "batch"]},
        },
        "rb-time-only": {
            "text": first_text("rb-time-only"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": False},
                   "reasons": [
                       "truncated at 384 tokens",
                       "the no_change fact is not stated",
                       "invents a task ('确保地下管道系统正常运行'), a detector "
                       "and a blockage",
                   ]},
        },
        "rb-conflict-two-actors": {
            "text": first_text("rb-conflict-two-actors"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": True},
                   "reasons": [
                       "echoes the input section labels ('场景：', '行动与"
                       "心理：', '可见动作：') into the prose",
                       "the second result text appears only as '肩膀抵住了钟"
                       "沿' after more than the frame's window, so it is not "
                       "checkable; the first result is paraphrased",
                       "adds invented inner speech and dialogue",
                   ]},
        },
        "rb-move-other-appearance": {
            "text": first_text("rb-move-other-appearance"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": True},
                   "reasons": [
                       "copies and then HALLUCINATES the record line: 'f0｜移动"
                       "｜钟面→钟楼边缘' and 'f0｜移动｜钟楼边缘→钟楼内部' do not "
                       "match the fact (管线镇→钟楼)",
                       "the actual move is never stated in prose",
                   ],
                   "observations": ["the worst format failure of the batch: the "
                                    "model treats the record line as copyable "
                                    "content and edits it"]},
        },
    },
    "summary": {
        "reviewed": 10,
        "n6Executed": 10,
        "n6Pass": 0,
        "n6Fail": 10,
        "n6Undetermined": 0,
        "d4Labeled": 10,
        "d4ProperNames": 1,
        "d4ProperNameList": ["老李"],
        "commonFindings": [
            "8/10 first calls ended normally (done_reason=stop); 2 still hit "
            "the 384 cap. The cap is no longer the dominant cause.",
            "no sample states the moved fact in a checkable form: the model "
            "opens inside the destination and never says 从…来到…",
            "outcome facts are paraphrased, not quoted (the frame requires the "
            "authoritative result text in the same sentence as the subject)",
            "format echo appears in 3 samples (section labels in rb-conflict, "
            "record lines in rb-move-other-appearance), one of them also "
            "hallucinating the record's values",
            "the only genuine D4 proper name is 老李 in rb-sanity-only; object "
            "and place descriptions are N6 notes under errata E5",
        ],
        "limit": "single reviewer; false negatives are not measurable here and "
                 "the verdicts are pending independent review",
    },
}

OUT.write_text(json.dumps(REVIEW, ensure_ascii=False, indent=1) + "\n",
               encoding="utf-8", newline="\n")
print(f"review -> {OUT}")
