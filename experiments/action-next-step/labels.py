# Action labels for the next-action classifier: 115 fine predicates in a frozen
# order, plus the 12 coarse groups derived from them (never the other way
# round). The coarse groups are a REPORTING projection: they are not what the
# model emits, and a 12-group hit never proves the full Y.
#
# The label file is the shared frozen copy at
# results/action-dataset-20261111/labels-v1.json. Its sha256 is registered in
# freeze.json, and this module refuses to build an index from a different file.

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Dict, List, Sequence, Tuple

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_LABELS = HERE.parents[3] / "results" / "action-dataset-20261111" / "labels-v1.json"
# parents: [0]=action-next-step [1]=experiments [2]=04-settlement [3]=worktrees

STEP_NONE = 0      # skip: an empty steps list, a real learnable class
STEP_ONE = 1
STEP_TWO = 2
STEP_CLASSES = 3
MAX_STEPS = 2

NULL_CANDIDATE = 0  # object pointer index for "no object"


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LabelIndex:
    """Fine predicate order + the derived coarse mapping.

    `fine` is the canonical order the model's 115-way heads use. It is sorted
    inside each coarse group and the groups keep the file's order, so the
    index is a pure function of the frozen label file and can be hashed.
    """

    def __init__(self, fine: Sequence[str], coarse_of: Sequence[int], groups: Sequence[str]):
        self.fine: List[str] = list(fine)
        self.coarse_of: List[int] = list(coarse_of)
        self.groups: List[str] = list(groups)
        self.fine_index: Dict[str, int] = {name: i for i, name in enumerate(self.fine)}
        if len(self.fine_index) != len(self.fine):
            raise ValueError("duplicate fine predicate")
        missing = [name for i, name in enumerate(self.fine) if not 0 <= self.coarse_of[i] < len(self.groups)]
        if missing:
            raise ValueError(f"fine predicate without coarse group: {missing[:3]}")

    def __len__(self) -> int:
        return len(self.fine)

    def action_id(self, name: str) -> int:
        if name not in self.fine_index:
            raise ValueError(f"fine predicate {name!r} is not in the frozen 115 list")
        return self.fine_index[name]

    def group_of_action(self, action_id: int) -> int:
        return self.coarse_of[action_id]

    def group_of_label(self, name: str) -> int:
        return self.coarse_of[self.action_id(name)]

    def digest(self) -> str:
        payload = json.dumps(
            {"fine": self.fine, "coarseOf": self.coarse_of, "groups": self.groups},
            ensure_ascii=False, sort_keys=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def summary(self) -> dict:
        counts = {name: 0 for name in self.groups}
        for coarse in self.coarse_of:
            counts[self.groups[coarse]] += 1
        return {
            "fine": len(self.fine),
            "coarse": len(self.groups),
            "groups": self.groups,
            "perGroup": counts,
            "digest": self.digest(),
        }


def load_labels(path: pathlib.Path | str | None = None) -> LabelIndex:
    path = pathlib.Path(path) if path else DEFAULT_LABELS
    data = json.loads(path.read_text(encoding="utf-8"))
    if int(data.get("fineActionCount", -1)) != 115:
        raise ValueError("labels file does not declare 115 fine predicates")
    if int(data.get("coarseActionCount", -1)) != 12:
        raise ValueError("labels file does not declare 12 coarse groups")
    fine: List[str] = []
    coarse_of: List[int] = []
    groups: List[str] = []
    for coarse_index, row in enumerate(data["groups"]):
        groups.append(str(row["group"]))
        for predicate in row["predicates"]:
            fine.append(str(predicate))
            coarse_of.append(coarse_index)
    if len(fine) != 115:
        raise ValueError(f"expected 115 fine predicates, found {len(fine)}")
    if len(set(fine)) != len(fine):
        raise ValueError("duplicate fine predicate in labels file")
    if str(data.get("playerFallbackLabel", "")) != "??":
        raise ValueError("player fallback label is not '??'")
    return LabelIndex(fine, coarse_of, groups)


def step_count_of(steps: Sequence[dict]) -> int:
    """0, 1 or 2. A third step is a data error, not something to truncate."""
    if len(steps) > MAX_STEPS:
        raise ValueError(f"y.steps has {len(steps)} steps; the protocol allows at most {MAX_STEPS}")
    return len(steps)


def coarse_pair(true_id: int, pred_id: int) -> Tuple[int, int]:
    return true_id, pred_id


if __name__ == "__main__":
    index = load_labels()
    print(json.dumps(index.summary(), ensure_ascii=False, indent=1))
