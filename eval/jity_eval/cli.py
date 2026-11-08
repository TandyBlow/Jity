"""Independent evaluation CLI; paid recording is isolated under explicit capture commands."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import webbrowser

from .runner import build_plan, create_run, execute, export_results, read_results
from .schema import validate_bundle


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="jity-eval", description="Jity Eval · 独立离线评测与显式授权游戏录制")
    subs = root.add_subparsers(dest="command", required=True)
    capture = subs.add_parser("capture", help="完整原始调用录制及严格离线重放", add_help=False)
    capture.add_argument("args", nargs=argparse.REMAINDER)
    replay = subs.add_parser("replay", help="冻结 Jity 剧情、离线回放与真实上下文审计", add_help=False)
    replay.add_argument("args", nargs=argparse.REMAINDER)
    for name in ("validate", "plan"):
        sub = subs.add_parser(name, help="校验用例和标准答案" if name == "validate" else "预览任务数量，不创建运行")
        sub.add_argument("config", type=Path)
    sub = subs.add_parser("run", help="创建并执行独立的离线任务")
    sub.add_argument("config", type=Path)
    sub.add_argument("--output", required=True, type=Path)
    sub.add_argument("--max-samples", type=int, help="本次最多执行多少样本；剩余可 resume")
    sub = subs.add_parser("resume", help="从冻结输入恢复，已评分样本不会重跑")
    sub.add_argument("run_dir", type=Path)
    sub.add_argument("--max-samples", type=int)
    sub.add_argument("--retry-errors", action="store_true", help="额外重试运行失败/评分失败，不重跑答错的样本")
    for name in ("status", "report"):
        sub = subs.add_parser(name, help="查看任务状态" if name == "status" else "重新生成自包含浏览器报告")
        sub.add_argument("run_dir", type=Path)
        if name == "report":
            sub.add_argument("--open", action="store_true", help="在本机默认浏览器打开报告")
    return root


def summary(result: dict) -> None:
    print("离线模拟 · 非模型评测成绩 · 真实模型调用 0")
    print("任务 %s · %s · 已处理 %s/%s" % (result["run_id"], result["status"], result["completed"], result["total"]))
    print(json.dumps(result["counts"], ensure_ascii=False))


def main(argv=None) -> int:
    values = sys.argv[1:] if argv is None else list(argv)
    if values and values[0] == "capture":
        from .capture.cli import main as capture_main
        return capture_main(values[1:])
    if values and values[0] == "replay":
        from .replay.cli import main as replay_main
        return replay_main(values[1:])
    args = parser().parse_args(argv)
    try:
        if args.command in ("validate", "plan"):
            config, suite, gold = validate_bundle(args.config)
            plan = build_plan(config, suite)
            print("校验通过 · 离线模拟 · 真实模型调用 0")
            print("%s：%s 剧本，%s 个题目，%s 个实验样本。" % (suite["title"], len(suite["cases"]), len(gold), len(plan)))
            if args.command == "plan":
                print("模式：%s；重复：%s；种子：%s；近期窗口：%s 回合。" %
                      (", ".join(config["modes"]), config["repeats"], config["seed"], config["recent_window"]))
            return 0
        if args.command == "run":
            if args.max_samples is not None and args.max_samples < 1:
                raise ValueError("max_samples 必须是正整数。")
            path = create_run(args.config, args.output)
            result = execute(path, args.max_samples)
        elif args.command == "resume":
            path = args.run_dir.resolve()
            result = execute(path, args.max_samples, args.retry_errors)
        elif args.command == "status":
            summary(read_results(args.run_dir))
            return 0
        else:
            from .report import render_report
            path = args.run_dir.resolve()
            export_results(path)
            report = render_report(path)
            print("浏览器报告：%s" % report)
            if args.open:
                webbrowser.open(report.as_uri())
            return 0
        summary(result)
        print("浏览器报告：%s" % (path / "report.html"))
        return 1 if result["counts"]["adapter_error"] or result["counts"]["grading_error"] else 0
    except KeyboardInterrupt:
        print("\n已中断。任务进度已保留，可用 resume 恢复。", file=sys.stderr)
        return 130
    except (ValueError, OSError, sqlite3.Error) as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return 2
