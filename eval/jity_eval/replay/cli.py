"""Independent replay commands. No service startup and no model transport."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import webbrowser

from ..storage import atomic_json
from .dataset import discover_sessions, freeze_dataset, load_dataset
from .sandbox import ReplayBoundaryError


def parser():
    root = argparse.ArgumentParser(prog="jity-eval replay", description="Jity 冻结剧情与真实上下文离线审计，真实模型调用 0")
    sub = root.add_subparsers(dest="command", required=True)
    item = sub.add_parser("inventory", help="只读列出存档活动分支")
    item.add_argument("database", type=Path)
    item = sub.add_parser("freeze", help="冻结一条活动祖先链，不修改原存档")
    item.add_argument("--jity-root", required=True, type=Path)
    item.add_argument("--database", required=True, type=Path)
    item.add_argument("--session")
    item.add_argument("--head")
    item.add_argument("--output", required=True, type=Path)
    item = sub.add_parser("extract", help="提取待人工复核的延迟探针，答案单独保存")
    item.add_argument("dataset", type=Path)
    item.add_argument("--output", required=True, type=Path)
    item.add_argument("--per-delay", type=int, help="每种延迟选取多少题；完整候选仍单独保留")
    item.add_argument("--annotations", type=Path)
    item = sub.add_parser("contexts", help="在三组独立分支组装真实 Jity 上下文，不生成答案")
    item.add_argument("dataset", type=Path)
    item.add_argument("--jity-root", required=True, type=Path)
    item.add_argument("--probes-dir", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    item.add_argument("--recent-window", type=int, default=5)
    item.add_argument("--budget", type=int, default=102400)
    item.add_argument("--repeats", type=int, default=1)
    item.add_argument("--max-samples", type=int)
    item = sub.add_parser("resume", help="恢复上下文任务，已完成样本不重跑")
    item.add_argument("run_dir", type=Path)
    item.add_argument("--max-samples", type=int)
    item.add_argument("--retry-errors", action="store_true")
    for command in ("status", "report"):
        item = sub.add_parser(command)
        item.add_argument("run_dir", type=Path)
        if command == "report":
            item.add_argument("--open", action="store_true")
    item = sub.add_parser("transitions", help="真实状态/记忆处理边界审计；缺辅助调用记录即停止")
    item.add_argument("dataset", type=Path)
    item.add_argument("--jity-root", required=True, type=Path)
    item.add_argument("--output", required=True, type=Path)
    item.add_argument("--committed-outputs", action="store_true", help="显式使用已提交剧情 JSON；不冒充原始模型响应")
    item.add_argument("--calls", type=Path, help="严格匹配的历史调用记录 JSON 数组")
    item.add_argument("--limit", type=int)
    return root


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _probe_document(directory):
    directory = Path(directory)
    return {**_load(directory / "probes.json"), **_load(directory / "gold.json"),
            "coverage": _load(directory / "coverage.json")}


def extract(dataset_path, output, per_delay=None, annotations=None):
    from .probes import extract_probes, validate_probes
    if per_delay is not None and per_delay < 1:
        raise ValueError("per-delay 必须是正整数")
    dataset = load_dataset(dataset_path)
    document = extract_probes(dataset, annotations=annotations)
    selected = document["probes"]
    if per_delay is not None:
        candidates = {row["fact_id"]: row for row in document["candidates"]}
        gold = {row["probe_id"]: row for row in document["gold"]}
        selected = []
        for delay in (10, 20, 40):
            rows = [p for p in document["probes"] if p["delay"] == delay]
            rows.sort(key=lambda p: (
                candidates[p["fact_id"]].get("field") not in {"description", "location", "current_location"},
                len(str(gold[p["id"]]["expected_value"])) < 5,
                p["source_turn"], p["fact_id"], p["kind"],
            ))
            # Prefer distinct fact/kind pairs over repeatedly probing one fact.
            seen = set()
            for probe in rows:
                key = (probe["fact_id"], probe["kind"])
                if key in seen:
                    continue
                seen.add(key)
                selected.append(probe)
                if len(seen) >= per_delay:
                    break
    selected_ids = {probe["id"] for probe in selected}
    gold = [row for row in document["gold"] if row["probe_id"] in selected_ids]
    validate_probes(dataset, selected, gold, annotations=annotations)
    output = Path(output).resolve()
    source_root = dataset.get("source", {}).get("jity_root")
    if source_root:
        source_root = Path(source_root).resolve()
        if output == source_root or source_root in output.parents:
            raise ValueError("探针导出目录不能位于 Jity 中")
    output.mkdir(parents=True, exist_ok=False)
    atomic_json(output / "probes.json", {"schema_version": 1, "probes": selected, "annotations": annotations})
    atomic_json(output / "gold.json", {"schema_version": 1, "gold": gold})
    atomic_json(output / "candidates.json", {"candidates": document["candidates"], "all_probes": document["probes"], "all_gold": document["gold"]})
    coverage = {**document["coverage"], "selected_probes": len(selected),
                "selected_by_delay": {str(delay): sum(p["delay"] == delay for p in selected) for delay in (10, 20, 40)},
                "selection": "all" if per_delay is None else "prefer descriptive facts; up to %s probes per delay" % per_delay}
    atomic_json(output / "coverage.json", coverage)
    return coverage


def _require_jity_python():
    if sys.version_info < (3, 11):
        raise ValueError("真实 Jity 集成需要 Python 3.11+ 及其后端依赖；可使用 /opt/anaconda3/envs/jity-backend/bin/python")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "inventory":
            print(json.dumps(discover_sessions(args.database), ensure_ascii=False, indent=2))
            return 0
        if args.command == "freeze":
            print(freeze_dataset(args.jity_root, args.database, args.session, args.output, args.head))
            return 0
        if args.command == "extract":
            print(json.dumps(extract(args.dataset, args.output, args.per_delay,
                                     _load(args.annotations) if args.annotations else None), ensure_ascii=False, indent=2))
            return 0
        if args.command == "transitions":
            _require_jity_python()
            from .transitions import audit_transitions
            if args.limit is not None and args.limit < 1:
                raise ValueError("limit 必须是正整数")
            result = audit_transitions(load_dataset(args.dataset), args.jity_root, args.output,
                                       args.committed_outputs, args.limit, _load(args.calls) if args.calls else None)
            print(json.dumps({key: value for key, value in result.items() if key != "jity_source"}, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "completed_boundary_audit" else 1
        from .runner import create_context_run, execute_context_run, export_results, verify_run
        if args.command in ("contexts", "resume"):
            _require_jity_python()
            if args.max_samples is not None and args.max_samples < 1:
                raise ValueError("max-samples 必须是正整数")
            if args.command == "contexts":
                run_dir = create_context_run(args.dataset, args.jity_root, args.output,
                                             _probe_document(args.probes_dir), args.recent_window, args.budget, args.repeats)
                result = execute_context_run(run_dir, args.max_samples)
            else:
                run_dir = args.run_dir
                result = execute_context_run(run_dir, args.max_samples, args.retry_errors)
            print("真实 Jity 上下文离线组装 · 未生成探针答案 · 真实模型调用 0")
            print(json.dumps({key: value for key, value in result.items() if key != "samples"}, ensure_ascii=False, indent=2))
            print("报告：%s" % (run_dir / "report.html"))
            return 1 if result["counts"]["error"] or result["counts"]["missing_call"] else 0
        verify_run(args.run_dir, verify_source=False)
        result = export_results(args.run_dir)
        if args.command == "status":
            print(json.dumps({key: value for key, value in result.items() if key != "samples"}, ensure_ascii=False, indent=2))
        else:
            from .report import render_report
            report = render_report(args.run_dir)
            print(report)
            if args.open:
                webbrowser.open(report.as_uri())
        return 0
    except KeyboardInterrupt:
        print("已中断；上下文任务可用 replay resume 恢复。", file=sys.stderr)
        return 130
    except ReplayBoundaryError as exc:
        print("回放已明确停止：%s" % exc, file=sys.stderr)
        return 1
    except (ValueError, OSError, ImportError) as exc:
        print("回放错误：%s" % exc, file=sys.stderr)
        return 2
