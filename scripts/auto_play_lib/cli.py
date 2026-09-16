"""CLI entry point for the auto-play script."""

import argparse
import random
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

from auto_play_lib.api import (
    APIError,
    api_get,
    create_session,
    generate_scene,
    generate_scene_with_retries,
)
from auto_play_lib.config import (
    DEFAULT_API_BASE_URL,
    DEFAULT_CAMPAIGN,
    DEFAULT_CONSTRAINTS,
    DEFAULT_FRONTEND_URL,
    DEFAULT_MODEL,
    DEFAULT_STORY_STYLE,
    CAMPAIGN_CONSTRAINTS,
    CAMPAIGN_STORY_STYLE,
    CAMPAIGN_ENTRY_ACTION,
    INITIAL_OPTIONS,
)
from auto_play_lib.formatting import fenced_json
from auto_play_lib.markdown_log import (
    append_block,
    append_turn,
    append_turn_error,
    write_header,
)
from auto_play_lib.options import active_goals_from_state, choose_option


def main() -> int:
    args = parse_args()
    if args.style is None:
        args.style = CAMPAIGN_STORY_STYLE if args.campaign else DEFAULT_STORY_STYLE
    if args.constraints is None:
        args.constraints = CAMPAIGN_CONSTRAINTS if args.campaign else DEFAULT_CONSTRAINTS
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

    if args.browser:
        return run_in_browser(args, output_path)

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

        previous_options = [CAMPAIGN_ENTRY_ACTION] if args.campaign else list(INITIAL_OPTIONS)
        selected_recent: list[str] = []
        active_goals = active_goals_from_state(session.get("state") or {})

        for turn in range(1, args.turns + 1):
            # Keep the runner moving by choosing from the options produced by the previous turn.
            selected_index, action, score = choose_option(previous_options, selected_recent, rng, active_goals)
            selected_recent.append(action)
            selected_recent = selected_recent[-12:]

            print(f"[run {run_number}/{args.runs}] turn {turn}/{args.turns}: {action[:60]}")
            try:
                response = generate_scene_with_retries(args, session_id, action)
            except APIError as exc:
                append_turn_error(output_path, run_number, turn, session_id, previous_options, selected_index, action, score, exc)
                print(f"生成失败：{exc}", file=sys.stderr)
                return 1

            append_turn(
                output_path, run_number, turn, session_id, previous_options,
                selected_index, action, score, response, active_goals,
            )

            output = response.get("output", {})
            active_goals = active_goals_from_state(response.get("state") or {})
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


def run_in_browser(args: argparse.Namespace, output_path: Path) -> int:
    """Create one campaign session, open the visible UI, and monitor its progress."""
    if args.runs != 1:
        print("浏览器模式一次运行一个可见会话；已忽略 --runs。", file=sys.stderr)

    try:
        session = (
            api_get(args.api_base_url, f"/sessions/{args.session_id}", args.timeout)
            if args.session_id else create_session(args)
        )
    except APIError as exc:
        verb = "恢复" if args.session_id else "创建"
        print(f"{verb}战役会话失败：{exc}", file=sys.stderr)
        return 1

    session_id = session["session_id"]
    params = urlencode({
        "autoplay": "1",
        "session": session_id,
        "turns": args.turns,
        "delay": max(0, int(args.delay * 1000)),
        "seed": args.seed,
    })
    browser_url = f"{args.frontend_url.rstrip('/')}/?{params}"
    append_block(output_path, [
        "# Browser Run 1", "",
        f"- session_id: `{session_id}`",
        f"- campaign: `{args.campaign or '自由模式'}`",
        f"- browser_url: {browser_url}", "",
    ])

    print(f"正在浏览器打开：{browser_url}")
    if not webbrowser.open(browser_url, new=1):
        print("未能自动打开浏览器，请手动复制上面的 URL。", file=sys.stderr)

    last_turn = -1
    last_anchors: list[str] = []
    connection_failures = 0
    try:
        while True:
            try:
                session_snapshot = api_get(args.api_base_url, f"/sessions/{session_id}", args.timeout)
                progress = api_get(args.api_base_url, f"/sessions/{session_id}/progress", args.timeout)
                if connection_failures:
                    print("[browser] 后端连接已恢复，继续监控。")
                connection_failures = 0
            except APIError as exc:
                connection_failures += 1
                if connection_failures == 1 or connection_failures % 10 == 0:
                    print(
                        f"[browser] 后端暂时不可用，等待重连 {connection_failures}/60：{exc}",
                        file=sys.stderr,
                    )
                if connection_failures >= 60:
                    print("监控在连续 60 次重连失败后停止；浏览器会话数据仍保留。", file=sys.stderr)
                    return 1
                time.sleep(max(1.0, args.monitor_interval))
                continue

            state = session_snapshot.get("state") or {}
            turn = int(state.get("turn") or 0)
            if turn != last_turn:
                goals = active_goals_from_state(state)
                print(f"[browser] turn {turn}/{args.turns} · 当前目标：{'；'.join(goals) or '无'}")
                last_turn = turn

            anchors = [str(item) for item in progress.get("revealed_anchors") or []]
            new_anchors = [item for item in anchors if item not in last_anchors]
            if new_anchors:
                print(f"[browser] 新触发锚点：{', '.join(new_anchors)}")
            last_anchors = anchors

            if turn >= args.turns:
                append_block(output_path, [
                    "# 浏览器自动跑剧情结束", "",
                    f"- finished_at: `{datetime.now().isoformat(timespec='seconds')}`",
                    f"- final_turn: `{turn}`",
                    f"- revealed_anchors: `{len(anchors)}`",
                    f"- session_id: `{session_id}`", "",
                ])
                print(f"完成：会话 {session_id} 已跑到第 {turn} 回合，共触发 {len(anchors)} 个锚点。")
                return 0
            time.sleep(max(1.0, args.monitor_interval))
    except KeyboardInterrupt:
        print("监控已停止；浏览器中的自动跑剧情可继续运行或手动暂停。")
        return 130


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automatically play Jity stories and record every generated turn.")
    parser.add_argument("--api-base-url", default=DEFAULT_API_BASE_URL, help="Backend API base URL.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model passed to the backend.")
    parser.add_argument("--runs", type=positive_int, default=1, help="Number of sessions to run (API mode only).")
    parser.add_argument("--turns", type=positive_int, default=300, help="Turns per session before restarting.")
    parser.add_argument("--output", type=Path, help="Markdown output path. Defaults to playtest_logs/auto_play_TIMESTAMP.md.")
    parser.add_argument("--seed", type=int, default=20260616, help="Random seed used for tie-breaking.")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay in seconds between turns.")
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout in seconds.")
    parser.add_argument("--retries", type=int, default=2, help="Retries for each generate request after the first attempt.")
    parser.add_argument("--style", default=None, help="Story style sent to generate endpoint. Defaults to a campaign-aware style.")
    parser.add_argument("--constraints", default=None, help="Story constraints sent to generate endpoint. Defaults to campaign continuity rules.")
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN, help="Campaign JSON filename. Use an empty string for free mode.")
    parser.add_argument("--session-id", default="", help="Resume and monitor an existing session in browser mode instead of creating a new one.")
    parser.add_argument("--browser", action="store_true", help="Run through the visible Jity browser UI and monitor progress.")
    parser.add_argument("--frontend-url", default=DEFAULT_FRONTEND_URL, help="Jity frontend URL used by --browser.")
    parser.add_argument("--monitor-interval", type=float, default=2.0, help="Browser-mode progress polling interval in seconds.")
    return parser.parse_args()


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("playtest_logs") / f"auto_play_{stamp}.md"
