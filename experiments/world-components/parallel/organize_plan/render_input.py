# -*- coding: utf-8 -*-
"""Render the N3 plan into the N4 prompt (the "simulated downstream input").

The prompt format is copied from the frozen controllability run
(experiments/world-components/organize_wording/train_controllability.py:
prompt_plan) so the next model arm is directly comparable to the old one:
same header lines, same fact lines, same requirements, only the plan JSON and
the source facts differ. This file calls no model.

Usage:
    python -X utf8 render_input.py --out runs/r1/downstream-inputs.jsonl
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def fact_line(fact: dict) -> str:
    kind = fact.get("kind")
    if kind == "moved":
        return f"{fact['factId']}｜移动｜{fact['name']}｜{fact['from']}→{fact['to']}｜方向={fact.get('direction', '平')}"
    if kind == "outcome":
        return f"{fact['factId']}｜结果｜{fact['name']}｜{fact['text']}"
    if kind == "appearance_changed":
        return f"{fact['factId']}｜外观｜{fact['name']}｜{fact['text']}"
    if kind == "sanity_changed":
        return f"{fact['factId']}｜理智｜{fact['name']}｜{fact['from']}→{fact['to']}"
    if kind == "task_achieved":
        return f"{fact['factId']}｜任务｜{fact['name']}｜{fact['goal']}"
    if kind == "personality_changed":
        return f"{fact['factId']}｜个性｜{fact['name']}｜{fact['text']}"
    if kind == "positioned_at":
        return f"{fact['factId']}｜位置｜{fact['name']}｜{fact['at']}"
    return f"{fact['factId']}｜{kind}｜{fact.get('name', '')}｜{fact.get('text', '')}"


def render_prompt(context: dict, facts: list[dict], plan: dict, authorized_edges: list[dict]) -> str:
    edges = plan.get("edges", [])
    rel = "；".join(
        f"{e['from']} before {e['to']}（{e.get('mode', 'optional')}）" for e in edges
    ) if edges else "无"
    lines = [
        "叙事任务。",
        f"地点={context.get('place', '')}",
        f"地点可见={context.get('visible', '')}",
        f"场景={context.get('scene', '')}",
        f"视角={context.get('viewpoint', '')}",
        f"授权关系={rel}",
        "事实（按顺序）：",
    ]
    lines += [fact_line(f) for f in facts]
    plan_json = json.dumps(
        {"groups": plan["groups"], "refs": plan["refs"], "edges": edges},
        ensure_ascii=False, separators=(",", ":"),
    )
    lines += [
        "表达计划：",
        plan_json,
        "要求：按计划的组和衔接写；组内可用逗号或分号，组间至少分号；edges 里 required 的关系必须写出，optional 可不写。",
        "要求：把全部事实写成一段连贯中文；按给定顺序；不新增人物、物品、地点、动作、关系；不写任务标题、数值、时长、字段名；不写代词，需要称呼时用姓名或承前省略。",
        "正文：",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="freeze/sources.json")
    ap.add_argument("--plans", default="freeze/plans-v1.jsonl")
    ap.add_argument("--contexts", default="freeze/contexts.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    here = Path(__file__).resolve().parent
    sources = {s["sourceId"]: s for s in json.loads((here / args.sources).read_text(encoding="utf-8"))["sources"]}
    contexts = json.loads((here / args.contexts).read_text(encoding="utf-8"))["contexts"]
    rows = []
    for line in (here / args.plans).read_text(encoding="utf-8").splitlines():
        p = json.loads(line)
        src = sources[p["sourceId"]]
        facts = [f for f in src["facts"] if f["factId"] in p["factsUsed"]]
        prompt = render_prompt(contexts[p["sourceId"]], facts, p["plan"], p["authorizedEdges"])
        rows.append({
            "sourceId": p["sourceId"],
            "family": p["family"],
            "planId": p["planId"],
            "shape": p["shape"],
            "factsUsed": p["factsUsed"],
            "plan": p["plan"],
            "prompt": prompt,
        })
    out = here / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"wrote {out} ({len(rows)} prompts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
