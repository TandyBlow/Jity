#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_STORY_STYLE = "黑暗学院奇幻，带一点黑色幽默，强调 NPC 反应。"
DEFAULT_CONSTRAINTS = "关键 NPC 不能突然死亡；不要跳出当前入学调查。"
INITIAL_ACTION = "愣住两秒，然后硬着头皮打招呼：“学姐好……那个，这里到底有什么不普通的？”"
INITIAL_OPTIONS = [
    INITIAL_ACTION,
    "下意识后退半步，抓紧行李箱拉杆：“等等，你怎么知道我的名字？这是什么整蛊节目吗？”",
    "试图挤出个笑脸，但声音有点抖：“照片？什么照片？我那张高考准考证上的照片可丑了……”",
]

PROGRESSION_KEYWORDS = {
    "推进": 12,
    "继续": 10,
    "前往": 10,
    "进入": 9,
    "调查": 9,
    "询问": 8,
    "确认": 7,
    "检查": 7,
    "追问": 7,
    "观察": 6,
    "打开": 6,
    "寻找": 6,
    "跟随": 6,
    "接受": 5,
    "核验": 5,
    "听证": 5,
    "取件": 5,
    "档案": 5,
    "图书馆": 5,
    "钟楼": 5,
    "任务": 5,
    "线索": 5,
    "通行卡": 4,
    "诺诺": 4,
}

PASSIVE_KEYWORDS = {
    "等待": -8,
    "拒绝": -7,
    "离开学院": -7,
    "回宿舍睡觉": -6,
    "开玩笑": -4,
    "装傻": -4,
    "沉默": -4,
    "逃跑": -4,
    "什么都不做": -10,
}


class APIError(RuntimeError):
    pass


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    output_path = args.output or default_output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    write_header(output_path, args)

    try:
        health = api_get(args.api_base_url, "/health", args.timeout)
    except APIError as exc:
        print(f"无法连接后端：{exc}", file=sys.stderr)
        print("请先启动后端：cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000", file=sys.stderr)
        return 1

    append_block(
        output_path,
        [
            "## 后端健康检查",
            "",
            fenced_json(health),
            "",
        ],
    )

    for run_number in range(1, args.runs + 1):
        session = create_session(args)
        session_id = session["session_id"]
        append_block(
            output_path,
            [
                f"# Run {run_number}",
                "",
                f"- session_id: `{session_id}`",
                f"- model: `{session.get('model', args.model)}`",
                f"- max_turns: `{args.turns}`",
                "",
            ],
        )

        previous_options = list(INITIAL_OPTIONS)
        selected_recent: list[str] = []

        for turn in range(1, args.turns + 1):
            # Keep the runner moving by choosing from the options produced by the previous turn.
            selected_index, action, score = choose_option(previous_options, selected_recent, rng)
            selected_recent.append(action)
            selected_recent = selected_recent[-12:]

            print(f"[run {run_number}/{args.runs}] turn {turn}/{args.turns}: {action[:60]}")
            try:
                response = generate_scene_with_retries(args, session_id, action)
            except APIError as exc:
                append_turn_error(output_path, run_number, turn, session_id, previous_options, selected_index, action, score, exc)
                print(f"生成失败：{exc}", file=sys.stderr)
                return 1

            append_turn(output_path, run_number, turn, session_id, previous_options, selected_index, action, score, response)

            output = response.get("output", {})
            previous_options = [str(option) for option in output.get("options", []) if str(option).strip()]
            if output.get("game_over"):
                append_block(
                    output_path,
                    [
                        "",
                        f"> Run {run_number} 在第 {turn} 轮触发 game_over：{output.get('game_over_reason') or '无原因'}",
                        "",
                    ],
                )
                break
            if not previous_options:
                # Fall back to an active investigation action if the model ever returns no options.
                previous_options = ["继续沿着当前最明确的线索推进调查，并主动询问在场 NPC 下一步应该做什么。"]

            if args.delay > 0:
                time.sleep(args.delay)

    append_block(
        output_path,
        [
            "# 自动跑剧情结束",
            "",
            f"- finished_at: `{datetime.now().isoformat(timespec='seconds')}`",
            "",
        ],
    )
    print(f"完成，日志已写入：{output_path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatically play Jity stories and record every generated turn.")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL, help="Backend API base URL.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model passed to the backend.")
    parser.add_argument("--runs", type=positive_int, default=3, help="Number of sessions to run.")
    parser.add_argument("--turns", type=positive_int, default=300, help="Turns per session before restarting.")
    parser.add_argument("--output", type=Path, help="Markdown output path. Defaults to playtest_logs/auto_play_TIMESTAMP.md.")
    parser.add_argument("--seed", type=int, default=20260616, help="Random seed used for tie-breaking.")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay in seconds between turns.")
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries for each generate request after the first attempt.")
    parser.add_argument("--style", default=DEFAULT_STORY_STYLE, help="Story style sent to generate endpoint.")
    parser.add_argument("--constraints", default=DEFAULT_CONSTRAINTS, help="Story constraints sent to generate endpoint.")
    return parser.parse_args()


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("playtest_logs") / f"auto_play_{stamp}.md"


def create_session(args: argparse.Namespace) -> dict[str, Any]:
    return api_post(args.api_base_url, "/sessions", {"model": args.model}, args.timeout)


def generate_scene(args: argparse.Namespace, session_id: str, action: str) -> dict[str, Any]:
    return api_post(
        args.api_base_url,
        f"/sessions/{session_id}/generate",
        {
            "player_action": action,
            "model": args.model,
            "style": args.style,
            "constraints": args.constraints,
        },
        args.timeout,
    )


def generate_scene_with_retries(args: argparse.Namespace, session_id: str, action: str) -> dict[str, Any]:
    attempts = max(0, args.retries) + 1
    last_error: APIError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return generate_scene(args, session_id, action)
        except APIError as exc:
            last_error = exc
            if attempt >= attempts:
                break
            wait_seconds = min(2 * attempt, 8)
            print(f"  请求失败，{wait_seconds}s 后重试 {attempt}/{attempts - 1}: {exc}", file=sys.stderr)
            time.sleep(wait_seconds)
    raise last_error or APIError("unknown generate error")


def api_get(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    request = Request(f"{base_url.rstrip('/')}{path}", method="GET")
    return send_request(request, timeout)


def api_post(base_url: str, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return send_request(request, timeout)


def send_request(request: Request, timeout: float) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
            detail = payload.get("detail") or body
        except json.JSONDecodeError:
            detail = body
        raise APIError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise APIError(str(exc.reason)) from exc
    except TimeoutError as exc:
        raise APIError("request timed out") from exc
    except json.JSONDecodeError as exc:
        raise APIError(f"invalid JSON response: {exc}") from exc


def choose_option(options: list[str], selected_recent: list[str], rng: random.Random) -> tuple[int | None, str, int]:
    clean_options = [option.strip() for option in options if option.strip()]
    if not clean_options:
        return None, "继续沿着当前最明确的线索推进调查，并主动询问在场 NPC 下一步应该做什么。", 0

    # Score options with a small seeded jitter so ties do not always pick the first button.
    scored = []
    for index, option in enumerate(clean_options, start=1):
        score = score_option(option)
        if option in selected_recent:
            score -= 5
        score += rng.randint(0, 2)
        scored.append((score, -index, index, option))

    best_score, _, best_index, best_option = max(scored)
    return best_index, best_option, best_score


def score_option(option: str) -> int:
    score = 0
    for keyword, weight in PROGRESSION_KEYWORDS.items():
        if keyword in option:
            score += weight
    for keyword, weight in PASSIVE_KEYWORDS.items():
        if keyword in option:
            score += weight
    if "？" in option or "?" in option:
        score += 2
    if "：" in option or ":" in option:
        score += 1
    return score


def write_header(path: Path, args: argparse.Namespace) -> None:
    append_block(
        path,
        [
            "# Jity 自动跑剧情记录",
            "",
            f"- started_at: `{datetime.now().isoformat(timespec='seconds')}`",
            f"- api_base_url: `{args.api_base_url}`",
            f"- model: `{args.model}`",
            f"- runs: `{args.runs}`",
            f"- turns_per_run: `{args.turns}`",
            f"- seed: `{args.seed}`",
            "",
            "选择策略：优先选择包含推进、继续、前往、调查、询问、检查、任务、地点、关键 NPC 或关键物品的选项；降低等待、拒绝、逃跑、沉默等被动选项权重。",
            "",
        ],
    )


def append_turn(
    path: Path,
    run_number: int,
    turn: int,
    session_id: str,
    previous_options: list[str],
    selected_index: int | None,
    action: str,
    score: int,
    response: dict[str, Any],
) -> None:
    output = response.get("output", {})
    state = response.get("state", {})
    # Write every turn immediately so a long 900-turn run still leaves a useful partial log.
    lines = [
        f"## Run {run_number} / Turn {turn}",
        "",
        f"- session_id: `{session_id}`",
        f"- source: `{response.get('source', '')}`",
        f"- model_output_id: `{response.get('model_output_id')}`",
        f"- used_model: `{response.get('used_model', '')}`",
        f"- selected_option: `{selected_index if selected_index is not None else 'fallback'}`",
        f"- selection_score: `{score}`",
        f"- selected_action: {action}",
        "",
        "### 本轮可选项",
        "",
        *format_options(previous_options, selected_index),
        "",
        "### 生成剧情",
        "",
        output.get("narration", "").strip() or "无",
        "",
        "### 对话",
        "",
        *format_dialogue(output.get("dialogue", [])),
        "",
        "### 状态变化",
        "",
        f"- current_location: {output.get('current_location') or state.get('current_location') or '未知'}",
        f"- sanity_delta: `{output.get('sanity_delta', 0)}`",
        f"- health_delta: `{output.get('health_delta', 0)}`",
        f"- game_over: `{output.get('game_over', False)}`",
        f"- game_over_reason: {output.get('game_over_reason') or '无'}",
        "",
        "### Context Memory 快照",
        "",
        *format_state(state),
        "",
        "### RAG Hits",
        "",
        *format_rag_hits(response.get("retrieved_chunks", [])),
        "",
        "### 下一轮选项",
        "",
        *format_options(output.get("options", []), None),
        "",
    ]
    append_block(path, lines)


def append_turn_error(
    path: Path,
    run_number: int,
    turn: int,
    session_id: str,
    previous_options: list[str],
    selected_index: int | None,
    action: str,
    score: int,
    exc: Exception,
) -> None:
    append_block(
        path,
        [
            f"## Run {run_number} / Turn {turn} 生成失败",
            "",
            f"- session_id: `{session_id}`",
            f"- selected_option: `{selected_index if selected_index is not None else 'fallback'}`",
            f"- selection_score: `{score}`",
            f"- selected_action: {action}",
            f"- error: `{exc}`",
            "",
            "### 本轮可选项",
            "",
            *format_options(previous_options, selected_index),
            "",
        ],
    )


def format_options(options: list[str], selected_index: int | None) -> list[str]:
    if not options:
        return ["- 无"]
    lines = []
    for index, option in enumerate(options, start=1):
        marker = " [SELECTED]" if selected_index == index else ""
        lines.append(f"{index}. {option}{marker}")
    return lines


def format_dialogue(dialogue: list[dict[str, Any]]) -> list[str]:
    if not dialogue:
        return ["- 无"]
    return [f"- **{line.get('speaker') or '未知'}**：{line.get('text') or ''}" for line in dialogue]


def format_state(state: dict[str, Any]) -> list[str]:
    if not state:
        return ["- 无"]
    player_status = state.get("player_status") or {}
    lines = [
        f"- turn: `{state.get('turn', 0)}`",
        f"- current_location: {state.get('current_location') or '未知'}",
        f"- sanity: `{state.get('sanity', '')}`",
        f"- health: `{state.get('health', '')}`",
        f"- player_status: {compact_mapping(player_status)}",
        f"- items: {compact_named_list(state.get('items', []))}",
        f"- npcs: {compact_named_list(state.get('npcs', []))}",
        f"- quests: {compact_named_list(state.get('quests', []))}",
        f"- world_facts: {compact_named_list(state.get('world_facts', []))}",
        "- recent_events:",
    ]
    recent_events = state.get("recent_events", [])
    if recent_events:
        lines.extend(f"  - {event}" for event in recent_events)
    else:
        lines.append("  - 无")
    return lines


def compact_named_list(items: list[dict[str, Any]]) -> str:
    if not items:
        return "无"
    parts = []
    for item in items[:12]:
        name = item.get("name") or "未命名"
        status = item.get("status") or item.get("relationship") or item.get("objective") or item.get("description") or "已记录"
        parts.append(f"{name}({status})")
    suffix = f"；另有 {len(items) - 12} 项" if len(items) > 12 else ""
    return "；".join(parts) + suffix


def compact_mapping(mapping: dict[str, Any]) -> str:
    parts = [f"{key}={value}" for key, value in mapping.items() if value]
    return "；".join(parts) if parts else "无"


def format_rag_hits(chunks: list[dict[str, Any]]) -> list[str]:
    if not chunks:
        return ["- 无"]
    lines = []
    for chunk in chunks:
        keywords = ", ".join(chunk.get("keywords", [])) or "无"
        content = str(chunk.get("content") or "").replace("\n", " ").strip()
        if len(content) > 180:
            content = f"{content[:177]}..."
        lines.append(
            f"- `{chunk.get('source_type')}` score `{chunk.get('score')}` importance `{chunk.get('importance', 3)}` "
            f"**{chunk.get('title')}** keywords: {keywords}；{content}"
        )
    return lines


def fenced_json(payload: Any) -> str:
    return "```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def append_block(path: Path, lines: list[str]) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines))
        if not lines or lines[-1] != "":
            file.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
