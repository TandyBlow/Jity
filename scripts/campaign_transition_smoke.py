#!/usr/bin/env python3
"""Run a four-step real-LLM transition smoke test for every bundled campaign.

The script makes short-lived campaign copies whose first session ends after two
turns, so the production HTTP path can exercise a real session boundary without
editing the source campaign files.  It writes both JSON evidence and a readable
Markdown transcript, then removes the temporary campaign copies.
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CAMPAIGN_FILES = (
    "default_campaign.json",
    "龙族Ⅰ_火之晨曦_campaign.json",
    "龙族Ⅱ_悼亡者之瞳_campaign.json",
    "龙族Ⅲ_黑月之潮_campaign.json",
)
STEPS = (
    ("开场", "（开场）观察当前环境与在场人物。"),
    ("继续", "继续"),
    ("推进到下一幕", "推进到下一幕"),
    ("下一幕继续", "继续"),
)
CONTAMINATION_MARKERS = (
    "不要跳出当前入学调查",
    "完成卡塞尔学院入学报到",
    "接路明非报到",
    "诺诺前来接应",
    "卡塞尔学院报到处大厅",
)


def api(base: str, method: str, path: str, payload: dict[str, Any] | None = None) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        base.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=240) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc


def names(state: dict[str, Any]) -> list[str]:
    return [str(item.get("name", "")) for item in state.get("npcs", []) if item.get("name")]


def normalize(text: str) -> str:
    return re.sub(r"\s+|[，。！？、；：“”‘’（）()…,.!?;:\-—]", "", text)


def repeated_opening(opening: str, continuation: str) -> bool:
    first = normalize(opening)
    second = normalize(continuation)
    return len(first) >= 60 and first[:60] in second


def load_recorded_prompt(db_path: Path, output_id: int) -> str:
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT input_text FROM model_outputs WHERE id = ?", (output_id,)
        ).fetchone()
    return str(row[0]) if row else ""


def create_smoke_copy(source: Path, suffix: str) -> tuple[Path, dict[str, Any]]:
    campaign = json.loads(source.read_text(encoding="utf-8"))
    campaign["title"] = f"{campaign.get('title', source.stem)} [transition-smoke]"
    for arc in campaign.get("arcs", []):
        for session in arc.get("sessions", []):
            session["max_turns_per_session"] = 2
    destination = source.with_name(f"_transition_smoke_{suffix}_{source.name}")
    destination.write_text(json.dumps(campaign, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination, campaign


def run_campaign(
    base: str,
    db_path: Path,
    source_name: str,
    smoke_name: str,
    campaign: dict[str, Any],
    model: str | None,
) -> dict[str, Any]:
    create_payload: dict[str, Any] = {
        "game_name": f"transition-smoke::{source_name}",
        "campaign_filename": smoke_name,
        "slot_name": "transition-smoke",
    }
    if model:
        create_payload["model"] = model
    created = api(base, "POST", "/sessions", create_payload)
    session_id = created["session_id"]
    results: list[dict[str, Any]] = []

    for index, (label, player_prompt) in enumerate(STEPS, start=1):
        payload: dict[str, Any] = {
            "player_action": player_prompt,
            "slot_name": "transition-smoke",
        }
        if model:
            payload["model"] = model
        generated = api(base, "POST", f"/sessions/{session_id}/generate", payload)
        progress = api(base, "GET", f"/sessions/{session_id}/progress")
        output = generated["output"]
        state = generated["state"]
        results.append(
            {
                "step": index,
                "label": label,
                "player_prompt": player_prompt,
                "recorded_prompt": load_recorded_prompt(db_path, generated["model_output_id"]),
                "source": generated["source"],
                "used_model": generated["used_model"],
                "latency_ms": generated.get("latency_ms"),
                "arc_index": progress.get("arc_index"),
                "session_index": progress.get("session_index"),
                "turn_in_session": progress.get("turn_in_session"),
                "location": state.get("current_location", ""),
                "npcs": names(state),
                "narration": output.get("narration", ""),
                "dialogue": output.get("dialogue", []),
                "options": output.get("options", []),
                "timeline_node_id": generated.get("timeline_node_id"),
            }
        )

    first_arc_sessions = campaign["arcs"][0]["sessions"]
    expected_first = first_arc_sessions[0]
    expected_next = first_arc_sessions[1]
    combined = "\n".join(step["narration"] for step in results)
    marker_hits = [marker for marker in CONTAMINATION_MARKERS if marker in combined]
    if source_name == "default_campaign.json":
        marker_hits = []

    checks = {
        "opening_is_scripted": results[0]["source"] == "scripted",
        "first_continue_uses_real_llm": results[1]["source"] == "llm",
        "advanced_to_next_session": results[1]["session_index"] == 1,
        "next_opening_is_scripted": results[2]["source"] == "scripted",
        "next_opening_matches_campaign": normalize(results[2]["narration"])
        == normalize(expected_next.get("opening_scene", "")),
        "next_location_matches_campaign": results[2]["location"]
        == expected_next.get("entry_state", {}).get("location", expected_next.get("name", "")),
        "next_continue_uses_real_llm": results[3]["source"] == "llm",
        "first_opening_not_repeated": not repeated_opening(results[0]["narration"], results[1]["narration"]),
        "next_opening_not_repeated": not repeated_opening(results[2]["narration"], results[3]["narration"]),
        "no_enrollment_campaign_contamination": not marker_hits,
        "recorded_prompts_match": all(s["player_prompt"] == s["recorded_prompt"] for s in results),
    }
    return {
        "campaign_file": source_name,
        "title": campaign.get("title", "").replace(" [transition-smoke]", ""),
        "session_id": session_id,
        "expected_first_session": expected_first.get("name", ""),
        "expected_next_session": expected_next.get("name", ""),
        "contamination_marker_hits": marker_hits,
        "checks": checks,
        "passed": all(checks.values()),
        "steps": results,
    }


def render_markdown(evidence: dict[str, Any]) -> str:
    lines = [
        "# 四战役真实 LLM 跨幕冒烟测试",
        "",
        f"- 执行时间：{evidence['executed_at']}",
        f"- API：`{evidence['base_url']}`",
        f"- 模型：`{evidence['model']}`",
        f"- 总结果：{'通过' if evidence['passed'] else '失败'}",
        "",
    ]
    for campaign in evidence["campaigns"]:
        lines.extend(
            [
                f"## {campaign['title']}",
                "",
                f"- 文件：`{campaign['campaign_file']}`",
                f"- 会话：`{campaign['session_id']}`",
                f"- 跨幕：{campaign['expected_first_session']} → {campaign['expected_next_session']}",
                f"- 判定：{'通过' if campaign['passed'] else '失败'}",
                "",
                "| 检查项 | 结果 |",
                "|---|---|",
            ]
        )
        for key, value in campaign["checks"].items():
            lines.append(f"| `{key}` | {'通过' if value else '失败'} |")
        lines.append("")
        for step in campaign["steps"]:
            lines.extend(
                [
                    f"### {step['step']}. {step['label']}",
                    "",
                    f"- 提示词：`{step['player_prompt']}`",
                    f"- 持久化提示词：`{step['recorded_prompt']}`",
                    f"- 来源 / 模型：`{step['source']}` / `{step['used_model']}`",
                    f"- 进度：arc={step['arc_index']}, session={step['session_index']}, turn={step['turn_in_session']}",
                    f"- 地点：{step['location'] or '未记录'}",
                    f"- 人物：{'、'.join(step['npcs']) or '无'}",
                    f"- 选项：{' / '.join(step['options']) or '无'}",
                    "",
                    "剧情：",
                    "",
                    step["narration"],
                    "",
                ]
            )
            if step["dialogue"]:
                lines.append("对话：")
                lines.append("")
                for item in step["dialogue"]:
                    lines.append(f"- {item.get('speaker', '未知')}：{item.get('text', '')}")
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--campaign-dir", type=Path, default=Path("backend/data/campaigns"))
    parser.add_argument("--database", type=Path, default=Path("backend/data/jity.sqlite3"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/smoke"))
    parser.add_argument("--model", default=None, help="Omit to use the backend's configured model")
    args = parser.parse_args()

    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    temporary: list[Path] = []
    campaigns: list[dict[str, Any]] = []
    try:
        health = api(args.base_url, "GET", "/health")
        for index, filename in enumerate(CAMPAIGN_FILES, start=1):
            source = args.campaign_dir / filename
            temp, data = create_smoke_copy(source, f"{stamp}-{index}")
            temporary.append(temp)
            print(f"[{index}/4] {filename}", flush=True)
            result = run_campaign(
                args.base_url, args.database, filename, temp.name, data, args.model
            )
            campaigns.append(result)
            print(f"  {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)

    used_models = sorted({s["used_model"] for c in campaigns for s in c["steps"]})
    evidence = {
        "executed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "base_url": args.base_url,
        "health": health,
        "model": ", ".join(used_models),
        "passed": len(campaigns) == len(CAMPAIGN_FILES) and all(c["passed"] for c in campaigns),
        "campaigns": campaigns,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"campaign-transition-smoke-{stamp}.json"
    md_path = args.output_dir / f"campaign-transition-smoke-{stamp}.md"
    json_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(evidence), encoding="utf-8")
    print(json_path)
    print(md_path)
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
