"""Explicitly authorized live capture, separate from existing offline commands."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
import webbrowser


def parser():
    p = argparse.ArgumentParser(prog="jity-eval capture", description="完整游戏原始调用录制与严格离线重放")
    subs = p.add_subparsers(dest="command", required=True)
    preview = subs.add_parser("plan", help="离线查看规模与预算")
    preview.add_argument("--jity-root", type=Path, required=True)
    record = subs.add_parser("record", help="创建冻结数据集并执行已授权采集")
    record.add_argument("--jity-root", type=Path, required=True)
    record.add_argument("--output", type=Path, required=True)
    record.add_argument("--budget-usd", type=float, required=True)
    record.add_argument("--approval", required=True, help="用户确认的预算与范围说明；不得包含密钥")
    record.add_argument("--smoke-only", action="store_true")
    resume = subs.add_parser("resume", help="用原始调用重建前缀后继续，不重掷或重复提交")
    resume.add_argument("dataset", type=Path)
    resume.add_argument("--smoke-only", action="store_true")
    replay = subs.add_parser("replay", help="阻断网络后从头重放所有原始调用")
    replay.add_argument("dataset", type=Path)
    replay.add_argument("--game")
    replay.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    report = subs.add_parser("report", help="重新生成自包含浏览器报告")
    report.add_argument("dataset", type=Path)
    report.add_argument("--open", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    from .runner import plan, create_dataset, collect, verify_dataset, execute_game, refresh_summary, replay_game_subprocess
    try:
        if args.command == "plan":
            print(json.dumps(plan(args.jity_root), ensure_ascii=False, indent=2))
            return 0
        if args.command == "record":
            out = create_dataset(args.jity_root, args.output, max_cost_usd=args.budget_usd, approval=args.approval)
            result = collect(out, smoke_only=args.smoke_only)
        elif args.command == "resume":
            result = collect(args.dataset, smoke_only=args.smoke_only)
        elif args.command == "report":
            result = refresh_summary(args.dataset)
            path = args.dataset.resolve() / "report.html"
            print(str(path))
            if args.open:
                webbrowser.open(path.as_uri())
            return 0
        else:
            manifest = verify_dataset(args.dataset)
            specs = [s for s in manifest["games"] if args.game is None or s["id"] == args.game]
            if not specs:
                raise ValueError("Unknown game: " + args.game)
            failed = False
            for spec in specs:
                if not (args.dataset / spec["id"] / "calls.sqlite3").exists():
                    if args.game:
                        raise ValueError("Selected game has no recorded raw calls")
                    continue
                if args.worker:
                    result = asyncio.run(execute_game(args.dataset, spec, replay=True))
                else:
                    result = replay_game_subprocess(args.dataset, spec["id"])
                print(json.dumps({"game": spec["id"], "replay": result}, ensure_ascii=False), flush=True)
                failed |= result["status"] != "passed"
            return int(failed)
        print(json.dumps({"status": result["status"], "completed_games": result["completed_games"], "budget": result["budget"]}, ensure_ascii=False), flush=True)
        return 0 if args.smoke_only or result["completed_games"] == 4 else 1
    except KeyboardInterrupt:
        print("Interrupted; durable action/call journal retained.", file=sys.stderr)
        return 130
    except Exception as exc:
        print("Capture stopped: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2
