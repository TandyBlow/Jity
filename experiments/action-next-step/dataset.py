# Dataset: jsonl rows -> tensors for the next-action classifier.
#
# One example carries:
#   X text        (serialize.render_x; one sequence)
#   candidate     texts (variable count; the object pointer's keys)
#   step target   0 / 1 / 2
#   action target 2 slots of fine-predicate index, -100 where absent
#   object target 2 slots of pointer index (0 = null, 1..n = candidate), -100
#                 where absent
#
# Masks are the whole point of the design: a skip row trains the step head only,
# a one-step row trains slot 1 only, and a row whose action has no object trains
# the pointer towards null. Silent truncation is not allowed: a row longer than
# the registered max length is an error the caller must resolve (see
# measure_tokens.py), and a step-2 target on a one-step row is a data error.

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence, Tuple

import torch

from labels import LabelIndex, MAX_STEPS, STEP_CLASSES, load_labels, step_count_of
from serialize import candidate_ids, object_index, render_candidate, render_x

IGNORE = -100

TokenizeFn = Callable[[Sequence[str], int], Dict[str, torch.Tensor]]
# (texts, max_len) -> {"input_ids": Long[B,L], "attention_mask": Long[B,L]}


@dataclass
class Example:
    row_id: str
    text: str
    candidates: List[str]
    step: int
    actions: List[int]
    objects: List[int]

    def to_json(self) -> dict:
        return {
            "rowId": self.row_id, "text": self.text, "candidates": self.candidates,
            "step": self.step, "actions": self.actions, "objects": self.objects,
        }


def read_rows(path: pathlib.Path | str) -> List[dict]:
    rows: List[dict] = []
    for line_no, line in enumerate(pathlib.Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_no}: row must be an object")
        rows.append(row)
    return rows


def build_example(row: dict, labels: LabelIndex) -> Example:
    row_id = str(row.get("rowId") or "")
    if not row_id:
        raise ValueError("row without rowId")
    y = row.get("y")
    if not isinstance(y, dict) or not isinstance(y.get("steps", []), list):
        raise ValueError(f"{row_id}: y must be an object with a steps list")
    steps = y.get("steps") or []
    count = step_count_of(steps)
    actions: List[int] = []
    objects: List[int] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"{row_id}: step {index + 1} must be an object")
        action = step.get("action")
        if not isinstance(action, str) or not action.strip():
            raise ValueError(f"{row_id}: step {index + 1} has no action")
        actions.append(labels.action_id(action.strip()))
        objects.append(object_index(row, step))
    return Example(
        row_id=row_id,
        text=render_x(row),
        candidates=[render_candidate(c) for c in (row.get("x") or {}).get("candidates") or []],
        step=count,
        actions=actions,
        objects=objects,
    )


def check_split_isolation(rows: Sequence[dict], *, allow_shared_goal: bool = False) -> None:
    """The three set names are train/validation/test and the goals must not
    cross them. This is a guard on the delivered file, not a substitute for
    01's own split audit."""
    seen: Dict[str, str] = {}
    for row in rows:
        split = str(row.get("split") or "")
        if split not in ("train", "validation", "test"):
            raise ValueError(f"{row.get('rowId')}: split must be train/validation/test, got {split!r}")
        key = split_goal_key(row)
        previous = seen.get(key)
        if previous and previous != split:
            raise ValueError(
                f"goal family {key!r} appears in both {previous} and {split} "
                f"(row {row.get('rowId')}); the sets must be isolated by goal"
            )
        if allow_shared_goal:
            continue
        seen[key] = split


def split_goal_key(row: dict) -> str:
    for key in ("goalFamily", "goalId", "goalIds", "goal"):
        value = row.get(key)
        if isinstance(value, list) and value:
            return "+".join(sorted(str(item) for item in value))
        if isinstance(value, str) and value.strip():
            return value.strip()
    x = row.get("x") or {}
    goals = x.get("goals") or x.get("goal")
    if isinstance(goals, list) and goals:
        return "|".join(sorted(str(goal) for goal in goals))
    if isinstance(goals, str) and goals.strip():
        return goals.strip()
    raise ValueError(f"{row.get('rowId')}: row has no goal identity, cannot isolate splits")


def collate(examples: Sequence[Example], tokenize: TokenizeFn, max_len: int) -> Dict[str, torch.Tensor]:
    texts = [example.text for example in examples]
    encoded = tokenize(texts, max_len)
    input_ids = encoded["input_ids"]
    attention_mask = encoded["attention_mask"]
    if input_ids.shape[1] > max_len:
        raise ValueError(f"tokenizer returned {input_ids.shape[1]} tokens, registered max is {max_len}")
    width = max((len(example.candidates) for example in examples), default=0)
    batch = len(examples)
    cand_ids = torch.zeros((batch, max(width, 1)), dtype=torch.long)
    cand_mask = torch.zeros((batch, max(width, 1)), dtype=torch.long)
    if width:
        cand_rows: List[str] = []
        for example in examples:
            padded = list(example.candidates) + [""] * (width - len(example.candidates))
            cand_rows.extend(padded)
        cand_enc = tokenize(cand_rows, max_len)
        cand_ids = cand_enc["input_ids"].view(batch, width, -1)
        cand_mask = cand_enc["attention_mask"].view(batch, width, -1)
        for index, example in enumerate(examples):
            cand_mask[index, len(example.candidates):, :] = 0
    step = torch.tensor([example.step for example in examples], dtype=torch.long)
    actions = torch.full((batch, MAX_STEPS), IGNORE, dtype=torch.long)
    objects = torch.full((batch, MAX_STEPS), IGNORE, dtype=torch.long)
    for index, example in enumerate(examples):
        if len(example.actions) > MAX_STEPS:
            raise ValueError(f"{example.row_id}: more than {MAX_STEPS} steps")
        for slot, action in enumerate(example.actions):
            actions[index, slot] = action
            objects[index, slot] = example.objects[slot]
        if example.step != len(example.actions):
            raise ValueError(f"{example.row_id}: step count {example.step} disagrees with {len(example.actions)} steps")
    return {
        "input_ids": input_ids, "attention_mask": attention_mask,
        "cand_ids": cand_ids, "cand_mask": cand_mask,
        "step": step, "actions": actions, "objects": objects,
    }


def make_tokenizer_fn(tokenizer, *, record_lengths: list | None = None) -> TokenizeFn:
    """Real tokenizer adapter. No truncation is passed to the tokenizer: the
    caller's max_len is checked after encoding so an over-long row fails loudly
    instead of being cut."""

    def tokenize(texts: Sequence[str], max_len: int) -> Dict[str, torch.Tensor]:
        encoded = tokenizer(
            list(texts), padding=True, truncation=False, return_tensors="pt",
            max_length=None,
        )
        if record_lengths is not None:
            record_lengths.extend(int(mask.sum()) for mask in encoded["attention_mask"])
        if encoded["input_ids"].shape[1] > max_len:
            longest = max(int(mask.sum()) for mask in encoded["attention_mask"])
            raise ValueError(
                f"a row is {longest} tokens, longer than the registered max {max_len}; "
                "measure the corpus and register a larger max instead of truncating"
            )
        return {"input_ids": encoded["input_ids"], "attention_mask": encoded["attention_mask"]}

    return tokenize


def step_counts(rows: Sequence[dict]) -> Dict[str, int]:
    counts = {"skip": 0, "one": 0, "two": 0}
    for row in rows:
        steps = ((row.get("y") or {}).get("steps") or [])
        counts[["skip", "one", "two"][step_count_of(steps)]] += 1
    return counts


def object_nulls(rows: Sequence[dict]) -> Dict[str, int]:
    total = 0
    nulls = 0
    for row in rows:
        y = row.get("y") or {}
        candidates = candidate_ids(row)
        for step in y.get("steps") or []:
            total += 1
            if object_index(row, step) == 0:
                nulls += 1
        if len(candidates) == 0 and y.get("steps"):
            pass
    return {"objectSlots": total, "nullObjects": nulls}
