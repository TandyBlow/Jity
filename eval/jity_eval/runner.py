"""Offline experiment scheduler. No Jity imports, network clients or API keys."""
from __future__ import annotations

import json
from pathlib import Path
import uuid

from . import __version__
from .offline import OfflineSession, grade
from .schema import validate_bundle
from .storage import atomic_json, connect, digest, digest_bytes, encode, event, initialize, now, run_lock

STATUSES = ("pending", "running", "passed", "failed", "adapter_error", "grading_error")


def build_plan(config: dict, suite: dict) -> list[dict]:
    samples = []
    suite_hash = digest(suite)
    # Interleave modes for each probe; repeat is independent of attempts/retries.
    for repeat in range(1, config["repeats"] + 1):
        for case in suite["cases"]:
            for probe in sorted(case["probes"], key=lambda p: (p["source_turn"] + p["delay"], p["id"])):
                for mode in config["modes"]:
                    identity = {"suite": suite_hash, "case_id": case["id"],
                                "probe_id": probe["id"], "mode": mode, "repeat": repeat,
                                "seed": config["seed"], "recent_window": config["recent_window"]}
                    samples.append({
                        "sample_id": digest(identity)[:24], "case_id": case["id"],
                        "case_title": case["title"], "probe_id": probe["id"],
                        "mode": mode, "repeat": repeat, "kind": probe["kind"],
                        "delay": probe["delay"], "checkpoint_turn": probe["source_turn"] + probe["delay"],
                        "question": probe["question"],
                    })
    return samples


def create_run(config_path: Path, run_dir: Path) -> Path:
    config, suite, gold = validate_bundle(Path(config_path))
    samples = build_plan(config, suite)
    run_dir = Path(run_dir).resolve()
    # Never overwrite an existing run, including a partially initialized one.
    run_dir.mkdir(parents=True, exist_ok=False)
    frozen = {**config, "suite": "suite.json", "gold": "gold.json"}
    gold_file = {"schema_version": 1, "records": list(gold.values())}
    inputs = {"config": frozen, "suite": suite, "gold": gold_file}
    for key, value in inputs.items():
        atomic_json(run_dir / "inputs" / (key + ".json"), value)
    manifest = {
        "schema_version": 1, "run_id": "offline-" + uuid.uuid4().hex[:12],
        "created_at": now(), "adapter": "offline", "tool_version": __version__,
        "suite_id": suite["suite_id"], "title": suite["title"],
        "config": {k: v for k, v in frozen.items() if k not in ("suite", "gold")},
        "input_hashes": {key: digest_bytes((run_dir / "inputs" / (key + ".json")).read_bytes()) for key in inputs},
        "simulation": True, "real_model_calls": 0,
        "limitations": "工具基础设施演示；模式差异来自固定字典策略，不是 Jity 或真实模型的效果。",
    }
    atomic_json(run_dir / "manifest.json", manifest)
    connection = connect(run_dir)
    try:
        initialize(connection)
        with connection:
            connection.execute("INSERT INTO meta VALUES('manifest',?)", (encode(manifest),))
            connection.execute("INSERT INTO meta VALUES('plan_hash',?)", (digest(samples),))
            for index, sample in enumerate(samples):
                connection.execute("INSERT INTO samples(id,ordinal,spec,updated_at) VALUES(?,?,?,?)",
                                   (sample["sample_id"], index, encode(sample), now()))
            event(connection, "created", {"samples": len(samples), "real_model_calls": 0})
    finally:
        connection.close()
    export_results(run_dir)
    return run_dir


def verify_inputs(run_dir: Path):
    if not (run_dir / "run.sqlite3").is_file():
        raise ValueError("运行目录缺少 run.sqlite3，不能恢复。")
    connection = connect(run_dir)
    try:
        row = connection.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()
        manifest = json.loads(row[0])
        if json.loads((run_dir / "manifest.json").read_text(encoding="utf-8")) != manifest:
            raise ValueError("manifest 已改变；拒绝把不同配置混入同一次实验。")
        if manifest["tool_version"] != __version__:
            raise ValueError("工具版本不一致；请使用原版本恢复或创建新任务。")
        for key, expected in manifest["input_hashes"].items():
            data = (run_dir / "inputs" / (key + ".json")).read_bytes()
            if digest_bytes(data) != expected:
                raise ValueError("冻结输入 %s 已改变；请创建新任务。" % key)
        config, suite, gold = validate_bundle(run_dir / "inputs" / "config.json")
        specs = [json.loads(r[0]) for r in connection.execute("SELECT spec FROM samples ORDER BY ordinal")]
        planned = build_plan(config, suite)
        expected_plan_hash = connection.execute("SELECT value FROM meta WHERE key='plan_hash'").fetchone()[0]
        if digest(specs) != expected_plan_hash or digest(planned) != expected_plan_hash:
            raise ValueError("实验任务计划已改变，无法安全恢复。")
        return config, suite, gold, manifest
    finally:
        connection.close()


def read_results(run_dir: Path) -> dict:
    run_dir = Path(run_dir).resolve()
    _, _, gold, manifest = verify_inputs(run_dir)
    connection = connect(run_dir)
    try:
        counts = {status: 0 for status in STATUSES}
        samples = []
        for row in connection.execute("SELECT * FROM samples ORDER BY ordinal"):
            spec = json.loads(row["spec"])
            value = json.loads(row["result"]) if row["result"] else {}
            counts[row["status"]] += 1
            spec.update(status=row["status"], attempts=row["attempts"],
                        expected_value=gold[spec["case_id"] + "/" + spec["probe_id"]]["expected_value"],
                        actual_value=value.get("value"), decision=value.get("decision"),
                        error=row["error"], trace_path=row["trace_path"])
            samples.append(spec)
        completed = sum(counts[s] for s in STATUSES if s not in ("pending", "running"))
        status = "running" if counts["running"] else "paused" if counts["pending"] else "completed_with_errors" if counts["adapter_error"] or counts["grading_error"] else "completed"
        return {"schema_version": 1, "run_id": manifest["run_id"], "status": status,
                "total": len(samples), "completed": completed, "counts": counts,
                "real_model_calls": 0, "samples": samples, "updated_at": now()}
    finally:
        connection.close()


def export_results(run_dir: Path) -> dict:
    result = read_results(run_dir)
    atomic_json(run_dir / "results.json", result)
    return result


def _inject(config: dict, spec: dict, stage: str, attempt: int) -> None:
    for injection in config.get("failure_injections", []):
        if injection["stage"] == stage and injection["attempt"] == attempt and all(
            injection[key] == spec[key] for key in ("case_id", "probe_id", "mode", "repeat")
        ):
            raise RuntimeError("离线故障注入：%s attempt=%s" % (stage, attempt))


def _checkpoint(run_dir: Path, case: dict, turn: int) -> dict:
    # Rebuild from frozen history rather than trusting an editable checkpoint
    # artifact. The JSON is an auditable export, not a second source of truth.
    session = OfflineSession()
    for entry in case["history"]:
        if entry["turn"] <= turn:
            session.ingest(entry)
    snapshot = session.checkpoint()
    checkpoint_id = digest({"case": case["id"], "turn": turn})[:20]
    path = run_dir / "checkpoints" / (checkpoint_id + ".json")
    atomic_json(path, {"case_id": case["id"], "turn": turn, "snapshot": snapshot,
                       "snapshot_hash": digest(snapshot), "simulation": True})
    return snapshot


def execute(run_dir: Path, max_samples: int | None = None, retry_errors: bool = False) -> dict:
    run_dir = Path(run_dir).resolve()
    if max_samples is not None and (type(max_samples) is not int or max_samples < 1):
        raise ValueError("max_samples 必须是正整数。")
    if not run_dir.is_dir():
        raise ValueError("运行目录不存在。")
    with run_lock(run_dir):
        config, suite, gold, _ = verify_inputs(run_dir)
        cases = {c["id"]: c for c in suite["cases"]}
        connection = connect(run_dir)
        try:
            with connection:
                interrupted = list(connection.execute("SELECT id,attempts FROM samples WHERE status='running'"))
                for row in interrupted:
                    connection.execute("UPDATE attempts SET status='interrupted',finished_at=? WHERE sample_id=? AND attempt=?",
                                       (now(), row["id"], row["attempts"]))
                connection.execute("UPDATE samples SET status='pending',updated_at=? WHERE status='running'", (now(),))
                if interrupted:
                    event(connection, "recovered_interrupted", {"sample_ids": [r["id"] for r in interrupted]})
                if retry_errors:
                    connection.execute("UPDATE samples SET status='pending',updated_at=? WHERE status IN ('adapter_error','grading_error')", (now(),))
                    event(connection, "retry_errors_requested", {})
            pending = list(connection.execute("SELECT * FROM samples WHERE status='pending' ORDER BY ordinal"))
            for row in pending[:max_samples]:
                spec = json.loads(row["spec"])
                attempt = row["attempts"] + 1
                with connection:
                    connection.execute("UPDATE samples SET status='running',attempts=?,updated_at=? WHERE id=?",
                                       (attempt, now(), row["id"]))
                    connection.execute("INSERT INTO attempts(sample_id,attempt,status,started_at) VALUES(?,?,'running',?)",
                                       (row["id"], attempt, now()))
                    event(connection, "sample_started", {"sample_id": row["id"], "attempt": attempt})
                export_results(run_dir)
                trace = {"sample_id": row["id"], "attempt": attempt, "simulation": True,
                         "real_model_calls": 0, "stage": "adapter"}
                result = None
                error = None
                stage = "adapter"
                try:
                    case = cases[spec["case_id"]]
                    probe = next(p for p in case["probes"] if p["id"] == spec["probe_id"])
                    snapshot = _checkpoint(run_dir, case, spec["checkpoint_turn"])
                    snapshot_hash = digest(snapshot)
                    fork = OfflineSession.fork(snapshot)
                    _inject(config, spec, "adapter", attempt)
                    trace.update(fork.probe(probe, spec["mode"], config["recent_window"]))
                    if digest(snapshot) != snapshot_hash:
                        raise RuntimeError("测试分支污染了检查点。")
                    trace["checkpoint_hash"] = snapshot_hash
                    trace["parent_checkpoint_unchanged"] = True
                    result = trace["parsed_draft"]
                    stage = "grader"
                    _inject(config, spec, "grader", attempt)
                    expected = gold[spec["case_id"] + "/" + spec["probe_id"]]["expected_value"]
                    trace["grading"] = grade(result, expected, spec["kind"])
                    status = trace["grading"]["status"]
                except Exception as exc:
                    status = "adapter_error" if stage == "adapter" else "grading_error"
                    error = "%s: %s" % (type(exc).__name__, exc)
                    trace["error"] = error
                trace.update(status=status, stage=stage, finished_at=now())
                relative_trace = "traces/%s-attempt-%s.json" % (row["id"], attempt)
                atomic_json(run_dir / relative_trace, trace)
                with connection:
                    connection.execute("UPDATE samples SET status=?,result=?,error=?,trace_path=?,updated_at=? WHERE id=?",
                                       (status, encode(result) if result is not None else None, error, relative_trace, now(), row["id"]))
                    connection.execute("UPDATE attempts SET status=?,error=?,trace_path=?,finished_at=? WHERE sample_id=? AND attempt=?",
                                       (status, error, relative_trace, now(), row["id"], attempt))
                    event(connection, "sample_finished", {"sample_id": row["id"], "attempt": attempt, "status": status})
                export_results(run_dir)
            with connection:
                event(connection, "execution_stopped", {"max_samples": max_samples})
        finally:
            connection.close()
            export_results(run_dir)
            from .report import render_report
            render_report(run_dir)
    return read_results(run_dir)
