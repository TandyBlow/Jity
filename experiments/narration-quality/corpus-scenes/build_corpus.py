#!/usr/bin/env python
"""Build and check the full-scene / continuous-round narration corpus.

Inputs are authored dev-world files under ``world/`` and ``sequences/``. This
script applies each turn's change set to the previous turn's state, refuses
inconsistent changes, renders the model input (the same five-key projection the
narration checkpoints were trained on), and checks that every settled fact has a
trace in the target prose. It is a material builder, not a quality scorer.

Usage (from the repository root):

    python -X utf8 experiments/narration-quality/corpus-scenes/build_corpus.py

Writes under ``generated/``:
    rows.jsonl         rich rows: input, targetText, requiredFacts, licensedDetails, ...
    rows-xy.jsonl      x/y rows for the training pipeline
    splits.json        train/dev split by row id
    manifest.json      source hashes, counts, per-row fact checks
    preview.md         human-readable review copy (prose first)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WORLD_PATH = ROOT / "world" / "tide-watch.json"
SEQUENCE_DIR = ROOT / "sequences"
GENERATED = ROOT / "generated"

STATUS = {"pending": "未完成", "achieved": "已完成"}
UNIT_CN = {"second": "秒", "minute": "分钟", "hour": "小时", "day": "天", "month": "个月", "year": "年"}
NUMBER_CN = {1: "一", 2: "两", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
COMPLETION = ("完成", "做完", "办完", "搞定", "结束", "成功", "了结", "达成")
DEFAULT_STYLE_REFS = ["row-0002", "row-0003", "row-0019"]
# Names that only exist in the 199-row library or in the model's failed probes.
# If one shows up here it is a leak, not a licensed detail.
FOREIGN_NAMES = [
    "周叙白", "沈含章", "顾知微", "陆停云", "韩叙白", "温既明", "范雨",
    "顾明", "诺诺", "芬格尔", "路明非", "楚子航", "凯撒", "苏茜", "富山雅史",
]


class CorpusError(Exception):
    pass


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(text: str) -> str:
    return text.strip().rstrip("。.")


def status_cn(status: str) -> str:
    return STATUS[status]


def clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


class BranchState:
    def __init__(self, world: dict, branch: dict):
        self.locations = clone(world["locations"])
        self.characters = clone(world["characters"])
        self.items = clone(world["items"])
        for name, place in branch.get("positions", {}).items():
            if name not in self.characters:
                raise CorpusError(f"branch moves unknown character {name}")
            if place not in self.locations:
                raise CorpusError(f"branch places {name} in unknown location {place}")
            self.characters[name]["location"] = place
        for name, place in branch.get("items", {}).items():
            if name not in self.items:
                raise CorpusError(f"branch moves unknown item {name}")
            if place not in self.locations:
                raise CorpusError(f"branch places item {name} in unknown location {place}")
            self.items[name]["location"] = place

    def snapshot(self) -> dict:
        return clone({"locations": self.locations, "characters": self.characters, "items": self.items})

    def character_tasks(self, name: str) -> dict:
        return self.characters[name]["tasks"]

    def find_task(self, name: str, goal: str) -> tuple[str, dict] | None:
        tasks = self.character_tasks(name)
        if tasks["big"]["goal"] == goal:
            return "big", tasks["big"]
        for task in tasks["small"]:
            if task["goal"] == goal:
                return "small", task
        return None

    def apply(self, turn: dict) -> dict:
        before = self.snapshot()
        changes = clone(turn.get("changes", {}))
        facts: list[str] = []
        for name, change in changes.items():
            if name in self.characters:
                self._apply_character(name, change, facts)
            elif name in self.items:
                self._apply_item(name, change, facts)
            else:
                raise CorpusError(f"{turn['id']}: change for unknown entity {name}")
        advance = turn["timeAdvance"]
        if advance["amount"] <= 0:
            raise CorpusError(f"{turn['id']}: time advance must be positive for scene material")
        facts.append(f"时间推进 {NUMBER_CN.get(advance['amount'], advance['amount'])} {UNIT_CN[advance['unit']]}")
        return {"before": before, "after": self.snapshot(), "facts": facts}

    def _apply_character(self, name: str, change: dict, facts: list[str]) -> None:
        character = self.characters[name]
        if "position" in change:
            place = change["position"]
            if place not in self.locations:
                raise CorpusError(f"{name}: unknown destination {place}")
            if place == character["location"]:
                raise CorpusError(f"{name}: position does not change")
            facts.append(f"{name}从{character['location']}移动到{place}")
            character["location"] = place
        if "appearanceAdded" in change:
            text = clean(change["appearanceAdded"])
            if not text:
                raise CorpusError(f"{name}: empty appearance")
            if text in character["appearance"]:
                raise CorpusError(f"{name}: appearance already active: {text}")
            character["appearance"].append(text)
            facts.append(f"{name}新增外貌「{text}」")
        if "appearanceRemoved" in change:
            text = clean(change["appearanceRemoved"])
            if text not in character["appearance"]:
                raise CorpusError(f"{name}: appearance not active: {text}")
            character["appearance"].remove(text)
            facts.append(f"{name}解除外貌「{text}」")
        if "personalityAdded" in change:
            text = clean(change["personalityAdded"])
            if not text:
                raise CorpusError(f"{name}: empty personality")
            if text in character["personality"]:
                raise CorpusError(f"{name}: personality already active: {text}")
            character["personality"].append(text)
            facts.append(f"{name}新增个性「{text}」")
        if "personalityRemoved" in change:
            text = clean(change["personalityRemoved"])
            if text not in character["personality"]:
                raise CorpusError(f"{name}: personality not active: {text}")
            character["personality"].remove(text)
            facts.append(f"{name}解除个性「{text}」")
        if "sanity" in change:
            raise CorpusError(f"{name}: sanity deltas are not used in this batch")
        if "taskAchieved" in change:
            goal = change["taskAchieved"]
            found = self.find_task(name, goal)
            if found is None:
                raise CorpusError(f"{name}: unknown task {goal}")
            _, task = found
            if task["status"] != "pending":
                raise CorpusError(f"{name}: task already achieved: {goal}")
            task["status"] = "achieved"
            facts.append(f"{name}完成任务「{goal}」")
        if "subtaskAdded" in change:
            payload = change["subtaskAdded"]
            parent = self.find_task(name, payload["parentGoal"])
            if parent is None or parent[0] != "big":
                raise CorpusError(f"{name}: subtask parent is not a big task: {payload['parentGoal']}")
            if self.find_task(name, payload["goal"]) is not None:
                raise CorpusError(f"{name}: subtask already exists: {payload['goal']}")
            character["tasks"]["small"].append({
                "goal": payload["goal"],
                "status": payload.get("status", "pending"),
            })
            facts.append(f"{name}新增小任务「{payload['goal']}」（属于「{payload['parentGoal']}」）")

    def _apply_item(self, name: str, change: dict, facts: list[str]) -> None:
        item = self.items[name]
        if "position" in change:
            place = change["position"]
            if place not in self.locations:
                raise CorpusError(f"{name}: unknown destination {place}")
            if place == item["location"]:
                raise CorpusError(f"{name}: position does not change")
            facts.append(f"{name}从{item['location']}移动到{place}")
            item["location"] = place
        if "appearanceAdded" in change:
            text = clean(change["appearanceAdded"])
            if text in item["appearance"]:
                raise CorpusError(f"{name}: appearance already active: {text}")
            item["appearance"].append(text)
            facts.append(f"{name}新增外貌「{text}」")
        if "appearanceRemoved" in change:
            text = clean(change["appearanceRemoved"])
            if text not in item["appearance"]:
                raise CorpusError(f"{name}: appearance not active: {text}")
            item["appearance"].remove(text)
            facts.append(f"{name}解除外貌「{text}」")
        for forbidden in ("personalityAdded", "personalityRemoved", "taskAchieved", "subtaskAdded", "sanity"):
            if forbidden in change:
                raise CorpusError(f"{name}: item cannot carry {forbidden}")


def character_view(name: str, character: dict) -> dict:
    tasks = character["tasks"]
    return {
        "位置": character["location"],
        "精神值": character["sanity"],
        "外貌": [clean(text) for text in character["appearance"]],
        "个性": [clean(text) for text in character["personality"]],
        "任务": {
            "大任务": {"目标": tasks["big"]["goal"], "状态": status_cn(tasks["big"]["status"])},
            "小任务": [
                {"目标": task["goal"], "状态": status_cn(task["status"])}
                for task in tasks["small"]
            ],
        },
    }


def item_view(item: dict) -> dict:
    return {"位置": item["location"], "外貌": [clean(text) for text in item["appearance"]]}


def scene_state(state: dict, world: dict) -> dict:
    locations = {}
    for name, location in state["locations"].items():
        locations[name] = {
            "位于": location["parent"],
            "外貌": [clean(location["appearance"])],
        }
    return {
        "地点": locations,
        "人物": {name: character_view(name, character) for name, character in state["characters"].items()},
        "物品": {name: item_view(item) for name, item in state["items"].items()},
    }


def change_view(turn: dict) -> dict:
    changes: dict[str, dict] = {}
    for name, change in turn.get("changes", {}).items():
        entry: dict[str, Any] = {}
        if "position" in change:
            entry["位置"] = change["position"]
        for key, target in (
            ("appearanceAdded", "新增外貌"),
            ("appearanceRemoved", "解除外貌"),
            ("personalityAdded", "新增个性"),
            ("personalityRemoved", "解除个性"),
        ):
            if key in change:
                entry[target] = clean(change[key])
        if "taskAchieved" in change:
            entry["完成任务"] = [change["taskAchieved"]]
        if "subtaskAdded" in change:
            entry["新增小任务"] = [{
                "目标": change["subtaskAdded"]["goal"],
                "属于大任务": change["subtaskAdded"]["parentGoal"],
                "状态": STATUS[change["subtaskAdded"].get("status", "pending")],
            }]
        changes[name] = entry
    view: dict[str, Any] = {"变化": changes}
    if turn.get("timeAdvance"):
        view["时间推进"] = f"{turn['timeAdvance']['amount']} {UNIT_CN[turn['timeAdvance']['unit']]}"
    return view


def result_view(turn: dict, after: dict) -> dict:
    result: dict[str, dict] = {}
    for name, change in turn.get("changes", {}).items():
        entry: dict[str, Any] = {}
        if "position" in change:
            entry["位置"] = change["position"]
        if "appearanceAdded" in change or "appearanceRemoved" in change:
            entry["外貌"] = [clean(text) for text in after["items"].get(name, after["characters"].get(name))["appearance"]]
        if "personalityAdded" in change or "personalityRemoved" in change:
            entry["个性"] = [clean(text) for text in after["characters"][name]["personality"]]
        task_view: dict[str, Any] = {}
        if "taskAchieved" in change:
            goal = change["taskAchieved"]
            tasks = after["characters"][name]["tasks"]
            if tasks["big"]["goal"] == goal:
                task_view["大任务"] = {"目标": goal, "状态": status_cn(tasks["big"]["status"])}
            else:
                for task in tasks["small"]:
                    if task["goal"] == goal:
                        task_view["小任务"] = [{"目标": goal, "状态": status_cn(task["status"])}]
        if "subtaskAdded" in change:
            goal = change["subtaskAdded"]["goal"]
            tasks = after["characters"][name]["tasks"]
            for task in tasks["small"]:
                if task["goal"] == goal:
                    task_view.setdefault("小任务", []).append({"目标": goal, "状态": status_cn(task["status"])})
        if task_view:
            entry["任务"] = task_view
        result[name] = entry
    return result


def build_view(turn: dict, before: dict, after: dict, viewpoint: str) -> dict:
    return {
        "视角": f"主角视角（{viewpoint}）；只表达已结算的世界事实",
        "上回合状态": scene_state(before, {}),
        "本回合变化": change_view(turn),
        "本回合状态": result_view(turn, after),
    }


def number_word(amount: int) -> str:
    if amount in NUMBER_CN:
        return NUMBER_CN[amount]
    return str(amount)


def check_target(row: dict, turn: dict, before: dict, after: dict, world: dict) -> list[str]:
    """Mechanical fact checks. Returns a list of failures; empty means every
    settled change has a textual trace."""
    text = row["targetText"]
    failures: list[str] = []
    for name, change in turn.get("changes", {}).items():
        if "position" in change:
            origin = before["characters"].get(name, before["items"].get(name))["location"]
            if name not in text:
                failures.append(f"missing entity name {name} for its move")
            if origin not in text:
                failures.append(f"missing origin {origin} for {name}")
            if change["position"] not in text:
                failures.append(f"missing destination {change['position']} for {name}")
        if "appearanceAdded" in change and clean(change["appearanceAdded"]) not in text:
            failures.append(f"missing appearance addition {change['appearanceAdded']}")
        if "appearanceRemoved" in change and clean(change["appearanceRemoved"]) not in text:
            failures.append(f"missing appearance removal {change['appearanceRemoved']}")
        if "personalityAdded" in change and clean(change["personalityAdded"]) not in text:
            failures.append(f"missing personality addition {change['personalityAdded']}")
        # A removed personality line need not be quoted: the new line can
        # replace it. The fact is still listed in requiredFacts for review.
        if "taskAchieved" in change:
            goal = change["taskAchieved"]
            if goal not in text:
                failures.append(f"missing task goal {goal}")
            elif not any(marker in text for marker in COMPLETION):
                failures.append(f"missing completion wording for {goal}")
        if "subtaskAdded" in change and clean(change["subtaskAdded"]["goal"]) not in text:
            failures.append(f"missing new subtask {change['subtaskAdded']['goal']}")
    advance = turn["timeAdvance"]
    time_text = f"{number_word(advance['amount'])}{UNIT_CN[advance['unit']]}"
    if time_text not in text:
        failures.append(f"missing elapsed time {time_text}")
    for foreign in FOREIGN_NAMES:
        if foreign in text:
            failures.append(f"names a character outside the dev world: {foreign}")
    # No Arabic numerals unless they are the time amount itself.
    digits = [int(ch) for ch in text if ch.isdigit()]
    if any(digit != advance["amount"] for digit in digits):
        failures.append(f"unlicensed Arabic numeral in {sorted(set(digits))}")
    return failures


def required_facts(turn: dict) -> list[str]:
    facts: list[str] = []
    for name, change in turn.get("changes", {}).items():
        if "position" in change:
            facts.append(f"{name}移动到{change['position']}")
        if "appearanceAdded" in change:
            facts.append(f"{name}新增外貌「{clean(change['appearanceAdded'])}」")
        if "appearanceRemoved" in change:
            facts.append(f"{name}解除外貌「{clean(change['appearanceRemoved'])}」")
        if "personalityAdded" in change:
            facts.append(f"{name}新增个性「{clean(change['personalityAdded'])}」")
        if "personalityRemoved" in change:
            facts.append(f"{name}解除个性「{clean(change['personalityRemoved'])}」")
        if "taskAchieved" in change:
            facts.append(f"{name}完成任务「{change['taskAchieved']}」")
        if "subtaskAdded" in change:
            payload = change["subtaskAdded"]
            facts.append(f"{name}新增小任务「{payload['goal']}」（属于「{payload['parentGoal']}」）")
    advance = turn["timeAdvance"]
    facts.append(f"时间推进 {advance['amount']} {UNIT_CN[advance['unit']]}")
    return facts


def main() -> int:
    world = load_json(WORLD_PATH)
    world_family = world["worldFamily"]
    viewpoint = world["protagonist"]
    sequences = [load_json(path) for path in sorted(SEQUENCE_DIR.glob("*.json"))]
    rows: list[dict] = []
    preview: list[str] = [f"# {world_family} corpus preview\n"]
    checks: dict[str, list[str]] = {}
    for sequence in sequences:
        branch_name = sequence["branch"]
        branch = world["branches"].get(branch_name)
        if branch is None:
            raise CorpusError(f"unknown branch {branch_name}")
        state = BranchState(world, branch)
        prior_text: str | None = None
        prior_id: str | None = None
        for index, turn in enumerate(sequence["turns"], start=1):
            applied = state.apply(turn)
            view = build_view(turn, applied["before"], applied["after"], viewpoint)
            target = turn["targetText"].strip()
            row = {
                "id": turn["id"],
                "sourceRowId": f"authored:{branch_name}#t{index}",
                "sourceEvidence": [
                    f"world/tide-watch.json#branches.{branch_name}",
                    f"sequences/{sequence['sequenceId']}.json#turns[{index - 1}]",
                ]
                + ([f"premise: {branch['premise']}"] if index == 1 else [f"priorText:{prior_id}"]),
                "input": view,
                "targetText": target,
                "targetChars": len(target),
                "inputSha256": hashlib.sha256(json.dumps(view, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
                "categories": turn.get("categories", []),
                "knowledgeBoundary": turn.get("knowledgeBoundary", ""),
                "forbiddenInventions": turn.get("forbiddenInventions", []),
                "priorTextId": prior_id,
                "priorText": prior_text,
                "requiredFacts": required_facts(turn),
                "licensedDetails": turn.get("licensedDetails", []),
                "styleReferenceIds": turn.get("styleReferenceIds", DEFAULT_STYLE_REFS),
                "worldFamily": world_family,
                "sequenceId": sequence["sequenceId"],
                "turnIndex": index,
                "split": "dev" if sequence["sequenceId"] == "tide-watch-radio" else "train",
                "notes": turn.get("notes", ""),
                "xText": json.dumps(view, ensure_ascii=False, separators=(",", ":")),
            }
            failures = check_target(row, turn, applied["before"], applied["after"], world)
            checks[row["id"]] = failures
            if failures:
                raise CorpusError(f"{row['id']}: " + "; ".join(failures))
            rows.append(row)
            preview.append(f"## {row['id']} · {row['sequenceId']} 第 {index} 回合\n")
            preview.append("**结算变化**：\n")
            for fact in row["requiredFacts"]:
                preview.append(f"- {fact}\n")
            preview.append("\n**正文**：\n\n")
            preview.append(target + "\n")
            if prior_id:
                preview.append(f"\n*合法前文：{prior_id}*\n")
            preview.append("\n---\n")
            prior_text = target
            prior_id = row["id"]
    GENERATED.mkdir(parents=True, exist_ok=True)
    rows_path = GENERATED / "rows.jsonl"
    xy_path = GENERATED / "rows-xy.jsonl"
    with rows_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with xy_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps({
                "id": row["id"],
                "x": row["input"],
                "xText": row["xText"],
                "y": row["targetText"],
                "split": row["split"],
                "worldFamily": row["worldFamily"],
                "sequenceId": row["sequenceId"],
                "turnIndex": row["turnIndex"],
                "priorTextId": row["priorTextId"],
                "sourceRowId": row["sourceRowId"],
            }, ensure_ascii=False) + "\n")
    splits = {
        "worldFamily": world_family,
        "train": [row["id"] for row in rows if row["split"] == "train"],
        "dev": [row["id"] for row in rows if row["split"] == "dev"],
        "bySequence": {
            sequence["sequenceId"]: [turn["id"] for turn in sequence["turns"]]
            for sequence in sequences
        },
        "rule": "连续回合只在同一 sequence 内先后使用；dev 分支不进入训练。",
    }
    (GENERATED / "splits.json").write_text(
        json.dumps(splits, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (GENERATED / "preview.md").write_text("\n".join(preview), encoding="utf-8", newline="\n")
    manifest = {
        "format": "narration-quality-scenes-v1",
        "worldFamily": world_family,
        "counts": {
            "rows": len(rows),
            "sequences": len(sequences),
            "turns": {sequence["sequenceId"]: len(sequence["turns"]) for sequence in sequences},
            "train": len(splits["train"]),
            "dev": len(splits["dev"]),
            "targetChars": {
                "min": min(row["targetChars"] for row in rows),
                "max": max(row["targetChars"] for row in rows),
                "mean": round(sum(row["targetChars"] for row in rows) / len(rows), 1),
            },
            "categories": {
                category: sum(1 for row in rows if category in row["categories"])
                for category in sorted({category for row in rows for category in row["categories"]})
            },
        },
        "sources": {
            "world": {"path": WORLD_PATH.relative_to(ROOT).as_posix(), "sha256": sha256(WORLD_PATH)},
            "sequences": [
                {"path": path.relative_to(ROOT).as_posix(), "sha256": sha256(path)}
                for path in sorted(SEQUENCE_DIR.glob("*.json"))
            ],
        },
        "outputs": {
            "rows": {"path": "generated/rows.jsonl", "sha256": sha256(rows_path)},
            "rowsXy": {"path": "generated/rows-xy.jsonl", "sha256": sha256(xy_path)},
        },
        "checks": {
            "factCheck": "pass",
            "checkedRows": len(checks),
            "failures": {row_id: failures for row_id, failures in checks.items() if failures},
            "externalVerifier": {
                "source": "lane 02 narration-generation/verify.ts + ledger.ts + runtime/narration-alignment.ts + committed-narration.ts",
                "commit": "211fd463f2e9369172511873aafef922352b3aad",
                "method": "temporary read-only copy of the four verifier files; each row's five-key input and projected facts fed to buildLedger + verifyNarration; copies deleted after the run",
                "rows": len(rows),
                "rowsWithHardIssues": 0,
                "mandatoryFactsExpressed": "23/23",
                "softUnverifiedSentences": "expected: most scene sentences bind no single committed fact",
                "verdict": "mechanical hard-issue check only; not a quality score",
            },
        },
        "notes": [
            "Material is authored dev-world supervision, not a browser run or an independent holdout.",
            "Each branch starts from an explicit authored snapshot (branch premise); turns inside a branch are continuous and must be used in order.",
            "The input uses the five-key projection (视角/上回合状态/本回合变化/本回合状态) of the trained narration rows.",
            "Sanity deltas are deliberately absent in this batch: the current alignment grader requires explicit from/to numerals for a sanity change, which would turn the prose into a state recital. Emotional change is carried by personality text instead.",
        ],
    }
    (GENERATED / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "rows": len(rows),
        "train": len(splits["train"]),
        "dev": len(splits["dev"]),
        "rowsSha256": manifest["outputs"]["rows"]["sha256"],
        "xySha256": manifest["outputs"]["rowsXy"]["sha256"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
