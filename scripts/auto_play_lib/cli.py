"""CLI entry point for the auto-play script."""

import argparse
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from auto_play_lib.api import (
    APIError,
    api_get,
    create_session,
    generate_scene,
    generate_scene_with_retries,
)
from auto_play_lib.config import (
    DEFAULT_API_BASE_URL,
    DEFAULT_CONSTRAINTS,
    DEFAULT_MODEL,
    DEFAULT_STORY_STYLE,
    INITIAL_OPTIONS,
)
from auto_play_lib.formatting import fenced_json
from auto_play_lib.markdown_log import (
    append_block,
    append_turn,
    append_turn_error,
    write_header,
)
from auto_play_lib.options import choose_option


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

