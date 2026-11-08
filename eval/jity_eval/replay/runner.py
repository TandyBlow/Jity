"""Resumable context assembly jobs, kept separate from model-answer scoring."""
from __future__ import annotations

import json
from pathlib import Path

from ..storage import atomic_json, connect, digest, digest_bytes, encode, now, run_lock
from .dataset import load_dataset
from .sandbox import MissingRecordedCall, ReplayBoundaryError, code_fingerprint, replay_sandbox

STATUSES = ("pending", "running", "assembled", "error", "missing_call")


def _evaluator_fingerprint():
    root = Path(__file__).resolve().parents[1]
    return digest({str(path.relative_to(root)): digest_bytes(path.read_bytes())
                   for path in sorted(root.rglob("*.py"))})


def create_context_run(dataset_path, jity_root, run_dir, probe_document, recent_window=5,
                       budget=102400, repeats=1):
    from .probes import validate_probes
    dataset = load_dataset(Path(dataset_path))
    validate_probes(dataset, probe_document["probes"], probe_document["gold"],
                    annotations=probe_document.get("annotations"))
    for name, value in (("recent_window", recent_window), ("budget", budget), ("repeats", repeats)):
        if type(value) is not int or value < 1:
            raise ValueError(name + " 必须是正整数")
    if not probe_document["probes"]:
        raise ValueError("没有可组装的探针；请检查覆盖范围或提供人工事实标注")
    jity_root, run_dir = Path(jity_root).resolve(), Path(run_dir).resolve()
    if run_dir == jity_root or jity_root in run_dir.parents:
        raise ValueError("上下文运行目录不能位于 Jity 中")
    source = code_fingerprint(jity_root)
    run_dir.mkdir(parents=True, exist_ok=False)
    inputs = {"dataset": dataset, "probes": {"probes": probe_document["probes"], "annotations": probe_document.get("annotations")},
              "gold": {"gold": probe_document["gold"]}, "source": source}
    for name, value in inputs.items():
        atomic_json(run_dir / "inputs" / (name + ".json"), value)
    config = {"jity_root": str(jity_root), "recent_window": recent_window, "budget": budget, "repeats": repeats}
    plan = []
    dataset_hash = digest(dataset)
    for repeat in range(1, repeats + 1):
        for probe in probe_document["probes"]:
            for mode in ("full", "recent", "state"):
                spec = {**probe, "probe_id": probe["id"], "mode": mode, "repeat": repeat}
                spec["id"] = digest({"probe": probe, "mode": mode, "repeat": repeat, "dataset": dataset_hash})[:24]
                plan.append(spec)
    manifest = {"schema_version": 2, "kind": "jity_context_replay", "created_at": now(),
                "simulation": False, "real_model_calls": 0, "config": config,
                "dataset_summary": {"source": dataset["source"], "turns": len(dataset["turns"]),
                                    "probes": len(probe_document["probes"]), "call_records": len(dataset.get("call_records", [])),
                                    "coverage": probe_document.get("coverage", {})},
                "input_hashes": {name: digest_bytes((run_dir / "inputs" / (name + ".json")).read_bytes()) for name in inputs},
                "source_sha256": source["sha256"], "evaluator_sha256": _evaluator_fingerprint(), "plan_sha256": digest(plan),
                "limitations": ["从已冻结历史检查点恢复，不代表全链路逐调用重演完成。",
                                "使用真实 Jity 记忆与提示词代码、本地检索；未重放原始向量检索或 Director。",
                                "不生成探针答案，不计算模型记忆正确率。",
                                "自动提取探针的语义重提可能漏检，review_required 保留待人工复核。",
                                "pending 记忆保持冻结快照状态，未伪造缺失的辅助模型响应。"]}
    atomic_json(run_dir / "manifest.json", manifest)
    db = connect(run_dir)
    try:
        db.executescript("""
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE jobs(id TEXT PRIMARY KEY,ordinal INTEGER UNIQUE,spec TEXT,status TEXT DEFAULT 'pending',
                attempts INTEGER DEFAULT 0,trace_path TEXT,error TEXT);
            CREATE TABLE attempts(id TEXT,attempt INTEGER,status TEXT,trace_path TEXT,error TEXT,
                PRIMARY KEY(id,attempt));
        """)
        with db:
            db.execute("INSERT INTO meta VALUES('manifest',?)", (encode(manifest),))
            for index, spec in enumerate(plan):
                db.execute("INSERT INTO jobs(id,ordinal,spec) VALUES(?,?,?)", (spec["id"], index, encode(spec)))
    finally:
        db.close()
    export_results(run_dir)
    return run_dir


def verify_run(run_dir, verify_source=True):
    run_dir = Path(run_dir).resolve()
    if not (run_dir / "run.sqlite3").is_file():
        raise ValueError("上下文运行目录缺少 run.sqlite3")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    db = connect(run_dir)
    try:
        stored = json.loads(db.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()[0])
        if manifest != stored:
            raise ValueError("上下文运行 manifest 已被修改")
        plan = [json.loads(row[0]) for row in db.execute("SELECT spec FROM jobs ORDER BY ordinal")]
        if digest(plan) != manifest["plan_sha256"]:
            raise ValueError("上下文实验计划已被修改")
    finally:
        db.close()
    for name, expected in manifest["input_hashes"].items():
        if digest_bytes((run_dir / "inputs" / (name + ".json")).read_bytes()) != expected:
            raise ValueError("冻结输入已被修改：" + name)
    if verify_source and code_fingerprint(Path(manifest["config"]["jity_root"]))["sha256"] != manifest["source_sha256"]:
        raise ValueError("Jity 源码已变化；请另建实验，不得混入已有运行")
    if verify_source and manifest.get("evaluator_sha256", _evaluator_fingerprint()) != _evaluator_fingerprint():
        raise ValueError("jity-eval 源码已变化；请使用原版本恢复或创建新实验")
    return manifest


def export_results(run_dir):
    run_dir = Path(run_dir).resolve()
    db = connect(run_dir)
    try:
        counts = {key: 0 for key in STATUSES}
        samples = []
        for row in db.execute("SELECT * FROM jobs ORDER BY ordinal"):
            counts[row["status"]] += 1
            samples.append({**json.loads(row["spec"]), "status": row["status"], "attempts": row["attempts"],
                            "trace_path": row["trace_path"], "error": row["error"]})
        status = "running" if counts["running"] else "paused" if counts["pending"] else "completed_with_errors" if counts["error"] or counts["missing_call"] else "completed"
        result = {"schema_version": 2, "kind": "jity_context_replay", "status": status,
                  "total": len(samples), "completed": len(samples) - counts["pending"] - counts["running"],
                  "counts": counts, "samples": samples, "real_model_calls": 0, "updated_at": now()}
        atomic_json(run_dir / "results.json", result)
        return result
    finally:
        db.close()


def execute_context_run(run_dir, max_samples=None, retry_errors=False):
    from .context import build_context
    from .report import render_report
    run_dir = Path(run_dir).resolve()
    if max_samples is not None and (type(max_samples) is not int or max_samples < 1):
        raise ValueError("max_samples 必须是正整数")
    with run_lock(run_dir):
        manifest = verify_run(run_dir)
        config = manifest["config"]
        dataset = json.loads((run_dir / "inputs/dataset.json").read_text(encoding="utf-8"))
        db = connect(run_dir)
        try:
            with db:
                db.execute("UPDATE attempts SET status='interrupted' WHERE status='running'")
                db.execute("UPDATE jobs SET status='pending' WHERE status='running'")
                if retry_errors:
                    db.execute("UPDATE jobs SET status='pending' WHERE status IN ('error','missing_call')")
            pending = list(db.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY ordinal"))
            with replay_sandbox(Path(config["jity_root"]), run_dir):
                for row in pending[:max_samples]:
                    spec = json.loads(row["spec"])
                    attempt = row["attempts"] + 1
                    with db:
                        db.execute("UPDATE jobs SET status='running',attempts=? WHERE id=?", (attempt, row["id"]))
                        db.execute("INSERT INTO attempts VALUES(?,?,'running',NULL,NULL)", (row["id"], attempt))
                    error = None
                    try:
                        # Gold/candidate evidence is never passed to the Jity context builder.
                        trace = build_context(dataset, spec["checkpoint_turn"], spec["question"], spec["mode"],
                                              config["recent_window"], config["budget"])
                        trace.update(probe_id=spec["probe_id"], review_required=spec.get("review_required", True),
                                     branch_id=row["id"], attempt=attempt)
                        status = "assembled"
                    except ReplayBoundaryError as exc:
                        status = "missing_call" if isinstance(exc, MissingRecordedCall) else "error"
                        error = str(exc)
                        trace = {"error": error, "boundary_error": type(exc).__name__, "real_model_calls": 0}
                    except Exception as exc:
                        status = "error"
                        error = "%s: %s" % (type(exc).__name__, exc)
                        trace = {"error": error, "real_model_calls": 0}
                    path = "traces/%s-attempt-%s.json" % (row["id"], attempt)
                    atomic_json(run_dir / path, trace)
                    with db:
                        db.execute("UPDATE jobs SET status=?,trace_path=?,error=? WHERE id=?", (status, path, error, row["id"]))
                        db.execute("UPDATE attempts SET status=?,trace_path=?,error=? WHERE id=? AND attempt=?",
                                   (status, path, error, row["id"], attempt))
                    export_results(run_dir)
        finally:
            db.close()
            export_results(run_dir)
            render_report(run_dir)
        # A run is tied to one checkout version, including uncommitted source.
        verify_run(run_dir)
    return export_results(run_dir)
