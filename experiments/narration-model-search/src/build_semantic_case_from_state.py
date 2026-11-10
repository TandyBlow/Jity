#!/usr/bin/env python3
"""Build a proposed tasks-case prompt from a real WorldState, without running a model.

The prompt text follows 04-settlement's buildTasksPrompt at a pinned commit. It is a
draft for 03/04 to confirm: the expected decisions stay absent, and this file never
claims a frozen contract. The purpose is to put the real 14-character/73-task scale
in front of the reviewers instead of a synthetic miniature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def name_of(state: dict[str, Any], entity_id: str) -> str:
    initial = state.get("initial") or {}
    for bucket in ("locations", "items", "characters"):
        entity = (initial.get(bucket) or {}).get(entity_id)
        if isinstance(entity, dict) and entity.get("name"):
            return str(entity["name"])
    return entity_id


def active_text(records: list[dict[str, Any]]) -> list[str]:
    return [str(record["text"]) for record in records
            if record.get("active") and record.get("text")]


def container_label(state: dict[str, Any], entity_id: str) -> str:
    position = ((state.get("items") or {}).get(entity_id) or {}).get("position")
    if not position:
        position = ((state.get("characters") or {}).get(entity_id) or {}).get("position")
    if not position:
        return "（无位置）"
    base = name_of(state, str(position.get("containerId", "")))
    if position.get("slotId"):
        base += "/" + str(position["slotId"])
    relative = position.get("relativeTo")
    if relative:
        base += f"（{relative.get('relation')} {name_of(state, str(relative.get('entityId', '')))}）"
    return base


def task_line(state: dict[str, Any], owner_id: str) -> str:
    character = ((state.get("characters") or {}).get(owner_id) or {})
    initial = ((state.get("initial") or {}).get("characters") or {}).get(owner_id) or {}
    appearance = [str(initial.get("initialAppearance") or "")]
    appearance += active_text(character.get("appearanceChanges") or [])
    personality = [str(initial.get("initialPersonality") or "")]
    personality += active_text(character.get("personalityChanges") or [])
    tasks = list((character.get("tasks") or {}).values())
    prefix = (f"- {initial.get('name') or owner_id}（id={owner_id}）位置={container_label(state, owner_id)}；"
              f"外貌={'；'.join(x for x in appearance if x)}；个性={'；'.join(x for x in personality if x)}")
    if not tasks:
        return prefix + "：无任务"
    rows = [f"{task.get('id')}：{task.get('goal')}（{'已完成' if task.get('status') == 'achieved' else '待办'}）"
            for task in tasks]
    return prefix + "：" + "；".join(rows)


def build_prompt(state: dict[str, Any], results: dict[str, str]) -> tuple[str, list[str], dict[str, list[str]]]:
    roster = sorted((state.get("characters") or {}).keys())
    rows = [task_line(state, owner) for owner in roster]
    required = sorted({owner for owner in roster
                       if ((state.get("characters") or {}).get(owner) or {}).get("tasks")})
    sample = required[0] if required else ""
    checklist = "、".join(f"{name_of(state, owner)}({owner})" for owner in required)
    skeleton = ",".join(f'{{"characterId":"{owner}","achieved":[]}}' for owner in required)
    example_id = sample or "人物id"
    result_text = "；".join(f"{key}：{value}" for key, value in results.items())
    now = (state.get("time") or {}).get("dateTime", "")
    prompt = "\n".join([
        "你是中文跑团游戏的任务判定器。只输出 JSON，不要解释。",
        "下面列出所有人物和他们的全部任务（包括已完成，也包括不在场人物）。请对每个人物给出一条决定。",
        "规则：",
        "- decisions 必须为每个有任务的人物各写一条，characterId 用括号里的 id 或人物全名；不能只写在场人物。",
        "- achieved 只列本轮新达成的任务 id；该人物其余任务保持原状，不要逐条输出 pending。",
        "- 没有新达成就写空数组；已完成的任务保持 achieved，不能改回 pending，也不要在 achieved 里重复列出。",
        "- 只有结算结果明确表明目标已经达成，才列入 achieved；只是尝试、接近、部分完成、被制止，都保持原状。",
        "- 行动结果里的 achieved 只描述那次行动，不等于任务完成；任务是否达成必须看目标本身。",
        f"当前世界时间：{now}",
        f"结算结果：{result_text or '（无）'}",
        "人物和任务：",
        *rows,
        f"有任务、必须各写一条的人物（{len(required)} 人）：{checklist}",
        f'输出 {{"decisions":[{skeleton}]}}（每个人物一条，achieved 只填本轮新达成的任务 id；没有就保留空数组）。示例 id 用 {example_id}。',
    ])
    allowed = {owner: sorted(((state.get("characters") or {}).get(owner) or {}).get("tasks", {}).keys())
               for owner in required}
    return prompt, required, allowed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True,
                        help="WorldState JSON, or a page turn JSON with a top-level state")
    parser.add_argument("--results", required=True,
                        help='JSON object mapping ids to settled result text, e.g. {"lu":"..."}')
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--pack-out", help="optional JSONL pack case for semantic_validate.py")
    parser.add_argument("--contract-commit", default="", help="04 commit this prompt was modelled from")
    parser.add_argument("--achieved", default="{}",
                        help='JSON object of newly achieved task ids, e.g. {"lu":["task_lu_goggles"]}')
    args = parser.parse_args()
    state_path = pathlib.Path(args.state)
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    state = raw.get("state") if isinstance(raw, dict) and isinstance(raw.get("state"), dict) else raw
    results = json.loads(args.results)
    if not isinstance(results, dict):
        raise SystemExit("--results must be a JSON object")
    achieved = json.loads(args.achieved)
    if not isinstance(achieved, dict):
        raise SystemExit("--achieved must be a JSON object")
    achieved = {str(owner): [str(task_id) for task_id in task_ids]
                for owner, task_ids in achieved.items()}
    prompt, required, allowed = build_prompt(state, {str(k): str(v) for k, v in results.items()})
    names = {str(entity.get("name")): character_id
             for character_id, entity in ((state.get("initial") or {}).get("characters") or {}).items()
             if entity.get("name")}
    allowed_ids = sorted(set((state.get("characters") or {}).keys())
                         | {task_id for tasks in allowed.values() for task_id in tasks})
    already = sorted(task.get("id")
                     for tasks in ((state.get("characters") or {}).values())
                     for task in (tasks.get("tasks") or {}).values()
                     if task.get("status") == "achieved")
    expected = {"decisions": [{"characterId": owner, "achieved": achieved.get(owner, [])}
                                for owner in required]}
    for owner, task_ids in achieved.items():
        if owner not in allowed:
            raise SystemExit(f"achieved owner {owner!r} has no tasks in this state")
        unknown = [task_id for task_id in task_ids if task_id not in allowed[owner]]
        if unknown:
            raise SystemExit(f"achieved task ids not owned by {owner}: {unknown}")
        repeated = [task_id for task_id in task_ids if task_id in already]
        if repeated:
            raise SystemExit(f"achieved task ids already achieved in the state: {repeated}")
    positive = any(achieved.values())
    case = {
        "caseId": args.case_id,
        "kind": "tasks",
        "source": str(state_path),
        "sourceSha256": sha256_file(state_path),
        "sourceStateHasTaskCount": sum(len(c.get("tasks") or {}) for c in (state.get("characters") or {}).values()),
        "sourceStateCharacterCount": len(state.get("characters") or {}),
        "prompt": prompt,
        "promptChars": len(prompt),
        "system": "",
        "user": prompt,
        "maxTokens": 520,
        "requiredCharacterIds": required,
        "allowedTaskIdsByCharacter": allowed,
        "expected": expected,
        "expectedStatus": ("proposed decisions from a constructed settled result; "
                            "03/04 must confirm before freeze") if positive else
                           ("proposed empty decisions (the settled result is a move only); "
                            "awaiting 03/04 confirmation; not a frozen case"),
        "expectedBasis": ("the settled result explicitly states the task goal was reached"
                           if positive else "the settled result contains no task achievement"),
        "constructedResult": positive,
        "correctedContract": False,
        "contractCommit": args.contract_commit,
        "allowedIds": allowed_ids,
        "nameToId": names,
        "allowUniqueNames": True,
        "alreadyAchievedTaskIds": already,
        "provenance": "generated from the real state by src/build_semantic_case_from_state.py; "
                      "prompt text follows 04-settlement buildTasksPrompt at the pinned source commit",
    }
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(case, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.pack_out:
        pack_case = dict(case)
        pack_case.pop("prompt", None)
        pack_path = pathlib.Path(args.pack_out)
        pack_path.parent.mkdir(parents=True, exist_ok=True)
        pack_path.write_text(json.dumps(pack_case, ensure_ascii=False) + chr(10), encoding="utf-8")
    print(f"{out}: {len(prompt)} chars, {len(required)} characters, "
          f"{sum(len(v) for v in allowed.values())} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
