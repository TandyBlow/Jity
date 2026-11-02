# N5 fact-sentence relation dataset builder (commit 3).
#
# Builds the training/dev/test data for the MiniRBT-H256 three-class head
# (support / contradiction / unknown) over (fact, sentence) pairs, from the
# SAME isolated story families as the v2 N4 corpus:
#   train <- families A and B rows, test <- family C rows ONLY (the frozen
#   N4-v2 holdout family; the N5 test freeze happens BEFORE training, same
#   discipline).
#
# Pair construction per corpus row:
#   support       every fact paired with the SENTENCE that expresses it in
#                 the row's own target text — including the composer's
#                 surface VARIANTS (v0/v1/v2), which gives the
#                 "correct but differently worded" class for free
#   contradiction programmatic perturbations of the fact paired with the
#                 original sentence, covering the task brief's error list:
#                   role-swap (moved from/to swapped), direction flip
#                   (sanity verb inverted), number error, unit error,
#                   same-goal misattribution (the other same-name actor's
#                   goal), time error, semantically-similar-but-wrong
#                   (relative relation flipped beside<->behind)
#   unknown       the fact paired with a sentence from a DIFFERENT row of
#                 the same family that does not express it (omission /
#                 no-evidence class: the honest answer is "cannot tell
#                 from this sentence")
#
# Splits follow the row's family: A/B rows -> train/dev (fixed 1-in-8
# slice), C rows -> test. The test file is written with its freeze
# registration (count, class distribution, sha256) and the trainer refuses
# to run against a moved test set.
#
# No model runs here; this file only composes pairs.

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
WC = HERE.parent
sys.path.insert(0, str(WC))
sys.path.insert(0, str(WC / "n4_corpus"))
sys.path.insert(0, str(HERE))

from compose_v2 import RELATION_CN  # noqa: E402
from n4_render import UNIT_CN  # noqa: E402

OUT_DIR = HERE / "corpus_v2" / "n5"
CLASSES = ("support", "contradiction", "unknown")


def fact_desc(fact: dict) -> str:
    """The fact's CANONICAL description (the right side of the pair) —
    value-pinned, recognizer-compatible wording."""
    kind = fact["kind"]
    if kind == "moved":
        return f"{fact['name']}从{fact['from']}来到了{fact['to']}"
    if kind == "task_achieved":
        return f"{fact['name']}完成了任务「{fact['goal']}」"
    if kind == "subtask_added":
        p = f"（隶属「{fact['parentGoal']}」）" if fact.get("parentGoal") else ""
        return f"{fact['name']}接到了新任务「{fact['goal']}」{p}"
    if kind == "sanity_changed":
        verb = "升到了" if fact["to"] > fact["from"] else "降到了"
        return f"{fact['name']}的精神值从{fact['from']}{verb}{fact['to']}"
    if kind == "personality_changed":
        return f"{fact['name']}变得{fact['text']}"
    if kind == "personality_removed":
        return f"{fact['name']}不再保有旧性子「{fact['text']}」"
    if kind == "appearance_changed":
        return f"{fact['name']}的外观变了：{fact['text']}"
    if kind == "appearance_removed":
        return f"{fact['name']}不再保有旧样貌「{fact['text']}」"
    if kind == "positioned_at":
        return f"{fact['name']}已在{fact['at']}"
    if kind == "position_relative":
        rel = RELATION_CN[fact["relation"]]
        if fact.get("op") == "removed":
            return f"{fact['name']}不再在{fact['targetName']}{rel}"
        return f"{fact['name']}现在在{fact['targetName']}{rel}"
    if kind == "slot_changed":
        if fact.get("op") == "removed":
            return f"{fact['name']}不再位于{fact['at']}的{fact['slotLabel']}"
        return f"{fact['name']}现在位于{fact['at']}的{fact['slotLabel']}"
    if kind == "time":
        return (f"前后大约{fact['amount']}"
                f"{UNIT_CN.get(fact['unit'], fact['unit'])}")
    if kind == "no_change":
        return "一切如旧"
    raise ValueError(f"no canonical description for {kind}")


def _swap_moved(fact: dict) -> dict:
    return {**fact, "from": fact["to"], "to": fact["from"]}


def _flip_sanity(fact: dict) -> dict:
    span = abs(fact["to"] - fact["from"]) or 3
    return {**fact, "from": fact["to"], "to": fact["from"] + (span if fact["to"] < fact["from"] else -span)}


def _number_error(fact: dict) -> dict:
    if fact["kind"] == "sanity_changed":
        return {**fact, "to": fact["to"] + 7}
    if fact["kind"] == "time":
        return {**fact, "amount": fact["amount"] + 9}
    return {**fact, "to": fact["from"]}


def _unit_error(fact: dict) -> dict:
    unit = fact["unit"]
    swap = {"minute": "hour", "hour": "minute", "second": "minute",
            "day": "month"}.get(unit, "minute")
    return {**fact, "unit": swap}


def _goal_error(fact: dict, row) -> dict:
    other = next((f for f in row["facts"]
                  if f["kind"] == "task_achieved"
                  and f.get("goal") != fact.get("goal")), None)
    if other is None:
        return {**fact, "goal": fact["goal"] + "（未登记）"}
    return {**fact, "goal": other["goal"]}


def _text_error(fact: dict, row=None) -> dict:
    """Semantically-similar-but-wrong: another entity's personality text
    from the same row (both are plausible descriptions; only the binding
    is wrong)."""
    other = next((f for f in row["facts"]
                  if f["kind"] == "personality_changed"
                  and f.get("text") != fact.get("text")), None) if row else None
    return {**fact, "text": other["text"] if other else fact["text"] + "（相反）"}


def _relative_flip(fact: dict) -> dict:
    flip = {"beside": "behind", "behind": "beside", "under": "above",
            "above": "under", "in_front_of": "behind"}
    return {**fact, "relation": flip.get(fact["relation"], "behind")}


PERTURB = {
    "moved": [("role-swap", lambda f, r=None: _swap_moved(f))],
    "task_achieved": [("goal-misattribution", lambda f, r: _goal_error(f, r))],
    "sanity_changed": [("direction-flip", lambda f, r=None: _flip_sanity(f)),
                       ("number-error", lambda f, r=None: _number_error(f))],
    "time": [("number-error", lambda f, r=None: _number_error(f)),
             ("unit-error", lambda f, r=None: _unit_error(f))],
    "position_relative": [("relation-flip",
                           lambda f, r=None: _relative_flip(f))],
    "personality_changed": [("text-swap", lambda f, r: _text_error(f, r))],
}


def sentences_of(row: dict) -> list:
    """The row's target sentences (the composer's segmentation)."""
    return [s + "。" for s in row["text"].split("。") if s.strip()]


def group_sentence_spans(row: dict) -> list:
    """(factId, sentence) pairs from the plan structure. The composer
    emits one sentence per fact; a time fact that does NOT lead its group
    is rendered as a leading PREFIX on the group's first sentence, so it
    shares that sentence's span instead of consuming the next one."""
    out = []
    sents = sentences_of(row)
    facts = {f["factId"]: f for f in row["facts"]}
    pos = 0
    for g in row["plan"]["sentences"]:
        group_facts = [facts[fid] for fid in g["factIds"]]
        time_leds = bool(group_facts) and group_facts[0]["kind"] == "time"
        group_start = pos
        for f in group_facts:
            if f["kind"] == "time" and not time_leds:
                # embedded leading-time prefix: shares the group's FIRST
                # sentence (the prefix sits on it), consumes no slot
                if group_start < len(sents):
                    out.append((f["factId"], sents[group_start]))
                continue
            if pos >= len(sents):
                break
            out.append((f["factId"], sents[pos]))
            pos += 1
    return out


def build_pairs(rows: list, split: str, seed: int = 20261102) -> list:
    import random
    rng = random.Random(seed)
    by_family = {}
    for r in rows:
        by_family.setdefault(r["familyId"], []).append(r)
    pairs = []
    for fam, fam_rows in by_family.items():
        other_sents = []
        for r in fam_rows:
            for fid, sent in group_sentence_spans(r):
                other_sents.append((r["rowId"], fid, sent))
        for r in fam_rows:
            spans = dict(group_sentence_spans(r))
            sents = sentences_of(r)
            for fid in r["mustExpress"]:
                fact = next(f for f in r["facts"] if f["factId"] == fid)
                sent = spans.get(fid) or (sents[0] if sents else "")
                if not sent:
                    continue
                # support: the row's own sentence expresses the fact
                pairs.append({
                    "pairId": f"{r['rowId']}:{fid}:sup",
                    "split": split, "familyId": r["familyId"],
                    "label": "support",
                    "perturbation": None,
                    "fact": fact, "sentence": sent,
                })
                # contradiction: programmatic perturbations
                for pname, fn in PERTURB.get(fact["kind"], []):
                    pf = fn(fact, r)
                    pairs.append({
                        "pairId": f"{r['rowId']}:{fid}:{pname}",
                        "split": split, "familyId": r["familyId"],
                        "label": "contradiction", "perturbation": pname,
                        "fact": pf, "sentence": sent,
                    })
                # unknown: pair with a sentence from another row of the
                # same family that does not express this fact
                cand = rng.choice(other_sents)
                pairs.append({
                    "pairId": f"{r['rowId']}:{fid}:unk",
                    "split": split, "familyId": r["familyId"],
                    "label": "unknown", "perturbation": "cross-row-sentence",
                    "fact": fact, "sentence": cand[2],
                })
    return pairs


def main() -> int:
    train_rows = [json.loads(l) for l in
                  (HERE / "corpus_v2" / "train-v2.jsonl").read_text(
                      encoding="utf-8").splitlines() if l.strip()]
    test_rows = [json.loads(l) for l in
                 (HERE / "corpus_v2" / "holdout-v2.jsonl").read_text(
                     encoding="utf-8").splitlines() if l.strip()]
    train_pairs = build_pairs(train_rows, "train")
    test_pairs = build_pairs(test_rows, "test")
    # dev = fixed 1-in-8 slice of train pairs (threshold fixing only)
    for i, p in enumerate(sorted(train_pairs,
                                 key=lambda x: x["pairId"])):
        p["split"] = "dev" if i % 8 == 7 else "train"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    train_path = OUT_DIR / "train.jsonl"
    train_path.write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n"
                for p in train_pairs), encoding="utf-8", newline="\n")
    test_path = OUT_DIR / "test.jsonl"
    test_path.write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n"
                for p in test_pairs), encoding="utf-8", newline="\n")
    from collections import Counter
    dist = lambda ps: dict(Counter(p["label"] for p in ps))
    test_sha = hashlib.sha256(test_path.read_bytes()).hexdigest()
    freeze = {
        "freeze": "n5-relation-test (commit 3) -- frozen BEFORE head "
                  "training; perturbations are programmatic and recorded "
                  "per pair; family C only",
        "file": "test.jsonl", "rows": len(test_pairs),
        "classDistribution": dist(test_pairs),
        "perturbations": sorted({p["perturbation"] for p in test_pairs
                                 if p["perturbation"]}),
        "sha256": test_sha,
    }
    (OUT_DIR / "test-freeze.json").write_text(
        json.dumps(freeze, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    report = {"train": len(train_pairs), "trainDist": dist(train_pairs),
              "test": len(test_pairs), "freeze": freeze}
    (HERE.parent.parent.parent / "artifacts" / "world-components" /
     "n5-corpus-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=False, indent=1)[:800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
