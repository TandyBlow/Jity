# Write the D4 labels and N6 verdicts for the first real-model batch.
#
# This is a REVIEW artefact, produced after the run: it is kept separate from
# the run archive so raw model output can never be confused with review notes.
# `apply_review.py` merges this file into the reviewed archive.
#
# The texts quoted in `d4.snippet` and the per-sample reasons refer to the FINAL
# model text of each sample (attempt 2 where a retry happened). The program
# template fallback is not reviewed and is never counted as model output.
#
# Usage: python -X utf8 write_review_v1.py

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
RUN = HERE / "out" / "real-batch-v1.json"
OUT = HERE / "fixtures" / "review-v1.json"

run = json.loads(RUN.read_text(encoding="utf-8"))
cases = {c["caseId"]: c for c in run["cases"]}


def last_text(cid):
    return cases[cid]["attempts"][-1]["output"]


REVIEW = {
    "version": "real-batch-v1-review",
    "batchId": run["batchId"],
    "reviewedAt": "2026-11-08",
    "reviewer": "assistant-manual (single reviewer, same session that ran the "
                "batch)",
    "reviewStatus": "pending-independent-review",
    "scope": "the FINAL model text of each sample (attempt 2 where a retry "
             "happened); the program-template fallback is NOT reviewed here and "
             "is never counted as model output",
    "d4Rule": "label a named person/item/place only when it is absent from the "
              "state registry AND absent from the authoritative text the model "
              "was given (task goals, resultText, appearance text). Generic "
              "nouns (木门, 楼梯, 窗户, 阳光, 雾气) are not named entities. "
              "isError=true only for genuinely invented names; names quoted "
              "from authoritative text are recorded with isError=false so the "
              "count stays separable.",
    "n6Rule": "A facts stated without contradiction; B no invented named "
              "entity/event/task-goal leak; C no other character's inner state; "
              "D complete and coherent. pass only when A-D hold; undetermined "
              "when unreadable.",
    "cases": {
        "rb-move-outcome": {
            "text": last_text("rb-move-outcome"),
            "d4": {"annotations": [
                {"snippet": "铜铃", "position": "第2段", "source": "human",
                 "reviewStatus": "pending-independent-review",
                 "isError": False,
                 "note": "quoted from the task goal; not registered as an item"},
            ]},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": False},
                   "reasons": [
                       "truncated mid-clause ('…将铜铃从肩上取下，铜')",
                       "no statement of the move 管线镇→钟楼",
                       "adds invented actions and an inner monologue that no "
                       "fact supports",
                   ]},
        },
        "rb-time-vague": {
            "text": last_text("rb-time-vague"),
            "d4": {"annotations": [
                {"snippet": "铁环", "position": "第2段", "source": "human",
                 "reviewStatus": "pending-independent-review", "isError": True,
                 "note": "invented object; not in the registry or the "
                         "authoritative text"},
                {"snippet": "铜铃", "position": "第2段", "source": "human",
                 "reviewStatus": "pending-independent-review", "isError": False,
                 "note": "quoted from the task goal"},
            ]},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": False},
                   "reasons": [
                       "truncated mid-clause ('…洒在管线甲的脸上，他微微')",
                       "the move and the completed result are not stated",
                       "'时间在这一刻仿佛静止了' is contradicted two clauses "
                       "later by '过去了一会儿'; that form is also not in the "
                       "gate vocabulary",
                   ]},
        },
        "rb-inner-change": {
            "text": last_text("rb-inner-change"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": False},
                   "reasons": [
                       "truncated mid-clause ('…这里已经不是他熟悉的管线镇')",
                       "none of the three changes is stated",
                       "adds an invented tension that no fact supports",
                   ]},
        },
        "rb-two-actors-move": {
            "text": last_text("rb-two-actors-move"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": False, "D": False},
                   "reasons": [
                       "truncated mid-clause ('…显得有些焦')",
                       "neither actor's move is stated",
                       "attributes intent to 管线乙 ('在催促着什么') — another "
                       "character's inner state",
                       "adds invented actions (跟在身后/加快脚步)",
                   ]},
        },
        "rb-same-name": {
            "text": last_text("rb-same-name"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": False, "D": False},
                   "reasons": [
                       "truncated mid-clause ('…但很快又消失')",
                       "three moves are not stated; the two 管线乙 collapse "
                       "into one continuous follower",
                       "attributes intent to 管线乙 ('似乎在催促着什么')",
                       "adds invented actions (跟/加快脚步/回头)",
                   ]},
        },
        "rb-subtask": {
            "text": last_text("rb-subtask"),
            "d4": {"annotations": [
                {"snippet": "梯子", "position": "第1-2段", "source": "human",
                 "reviewStatus": "pending-independent-review", "isError": False,
                 "note": "quoted from the subtask goal 找梯子"},
            ]},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": False},
                   "reasons": [
                       "truncated mid-clause ('终于，在钟楼的')",
                       "the move and the new subtask are not stated",
                       "adds invented actions (推门/攀爬/寻找)",
                   ]},
        },
        "rb-sanity-only": {
            "text": last_text("rb-sanity-only"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": False},
                   "reasons": [
                       "truncated mid-clause ('…无数个可能的场景在他脑海中')",
                       "the sanity drop and the personality change are not "
                       "stated in any checkable form",
                       "invents an inner monologue and a threat",
                   ]},
        },
        "rb-time-only": {
            "text": last_text("rb-time-only"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": False},
                   "reasons": [
                       "truncated mid-clause ('管线甲深吸')",
                       "the no_change fact is not stated; '一分一秒' adds a "
                       "duration claim the fact does not authorize",
                       "adds invented actions (环顾/挪动/寻找)",
                   ]},
        },
        "rb-conflict-two-actors": {
            "text": last_text("rb-conflict-two-actors"),
            "d4": {"annotations": [
                {"snippet": "广场", "position": "第1段", "source": "human",
                 "reviewStatus": "pending-independent-review", "isError": True,
                 "note": "invented place; the registry has no 广场"},
            ]},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": False, "D": False},
                   "reasons": [
                       "truncated mid-quote ('“准备好了吗？”我轻')",
                       "switches to first person ('我，管线甲'), violating the "
                       "third-person limited POV",
                       "attributes 急躁 to 管线乙 and narrates his inner state",
                       "adds invented dialogue, which the narrative contract "
                       "forbids",
                       "neither result text is stated",
                   ]},
        },
        "rb-move-other-appearance": {
            "text": last_text("rb-move-other-appearance"),
            "d4": {"annotations": []},
            "n6": {"status": "executed", "result": "fail",
                   "rubric": {"A": False, "B": False, "C": True, "D": False},
                   "reasons": [
                       "truncated mid-clause ('…确保没有遗漏')",
                       "leaks the input record verbatim ('f0｜移动｜管线甲｜"
                       "管线镇→钟楼') — a format violation",
                       "the move is not stated in prose",
                   ]},
        },
    },
    "summary": {
        "reviewed": 10,
        "n6Executed": 10,
        "n6Pass": 0,
        "n6Fail": 10,
        "n6Undetermined": 0,
        "d4Labeled": 10,
        "d4LabelsWithIsErrorTrue": 2,
        "d4LabelsQuotedFromAuthority": 3,
        "commonFindings": [
            "all 10 final texts stop at the pre-registered num_predict=128 cap "
            "(done_reason=length); every text is truncated mid-clause",
            "no sample states its required facts in a checkable form; the model "
            "writes atmosphere and inner monologue instead",
            "two samples narrate another character's inner state; one switches "
            "to first person; one leaks the input record verbatim",
            "two genuinely invented names (铁环, 广场); three names quoted from "
            "the authoritative text (铜铃 x2, 梯子)",
        ],
        "limit": "a single reviewer cannot measure their own misses; the "
                 "verdicts are pending independent review",
    },
}

OUT.write_text(json.dumps(REVIEW, ensure_ascii=False, indent=1) + "\n",
               encoding="utf-8", newline="\n")
print(f"review -> {OUT}")
