"""Gated collection: durable intentions, prefix reconstruction, exact offline replay."""
from __future__ import annotations

import asyncio
from contextlib import nullcontext
from copy import deepcopy
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from ..storage import atomic_json, digest, digest_bytes, now, run_lock
from .strategy import choose, coverage

DEFAULT_LIMITS = {"max_cost_usd": 10.0, "max_attempts": 850,
                  "max_input_tokens": 12000000, "max_output_tokens": 3000000,
                  "max_unpriced_attempts": 15}
PRICES = {"deepseek-flash": {"input_per_million": 0.30, "output_per_million": 1.20,
                             "cached_input_per_million": 0.006}}
GAME_SPECS = [
    {"id": "smoke", "kind": "smoke", "strategy": "mission", "seed": 7300, "turn_limit": 8},
    {"id": "game-01", "kind": "game", "strategy": "mission", "seed": 7301, "turn_limit": 80},
    {"id": "game-02", "kind": "game", "strategy": "explore", "seed": 7302, "turn_limit": 80},
    {"id": "game-03", "kind": "game", "strategy": "items", "seed": 7303, "turn_limit": 80},
    {"id": "game-04", "kind": "game", "strategy": "risk", "seed": 7304, "turn_limit": 80},
]


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tree_hash(root):
    root = Path(root)
    return {str(p.relative_to(root)): digest_bytes(p.read_bytes()) for p in sorted(root.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}


def _copy_tree(source, destination):
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".env", ".DS_Store"))


def plan(jity_root):
    """No credentials or external requests are needed for planning."""
    root = Path(jity_root).resolve()
    campaign = read_json(root / "backend/data/campaigns/default_campaign.json")
    return {"kind": "full_game_capture_plan", "campaign": campaign.get("title"),
            "max_turns_per_game": 80, "max_turns_per_campaign": 50, "smoke_turn_limit": 8,
            "games": GAME_SPECS, "limits": DEFAULT_LIMITS,
            "llm_model": "deepseek-flash", "thinking": "disabled", "http_max_retries": 2,
            "prices_usd_per_million": PRICES,
            "price_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "estimated_requests": [450, 800], "estimated_usd": [3, 8],
            "paid_player_model": False, "real_requests_started": 0}


def create_dataset(jity_root, dataset_dir, *, max_cost_usd, approval):
    """Freeze source/resources without .env or credentials. Never overwrite."""
    root, out = Path(jity_root).resolve(), Path(dataset_dir).resolve()
    if out == root or root in out.parents:
        raise ValueError("Capture output must be outside Jity.")
    if max_cost_usd <= 0 or not approval.strip():
        raise ValueError("Explicit positive budget and approval provenance are required.")
    out.mkdir(parents=True, exist_ok=False)
    frozen = out / "sources/Jity"
    (frozen / "backend/data/campaigns").mkdir(parents=True)
    _copy_tree(root / "backend/app", frozen / "backend/app")
    _copy_tree(root / "knowledge", frozen / "knowledge")
    for name in ("RULEBOOK.md", "backend/requirements.txt", "backend/requirements-dev.txt"):
        if (root / name).is_file():
            shutil.copy2(root / name, frozen / name)
    shutil.copy2(root / "backend/data/campaigns/default_campaign.json", frozen / "backend/data/campaigns/default_campaign.json")
    evaluator = Path(__file__).resolve().parents[1]
    _copy_tree(evaluator, out / "sources/evaluator/jity_eval")
    cache = Path(os.environ.get("TIKTOKEN_CACHE_DIR", os.environ.get("DATA_GYM_CACHE_DIR", str(Path(tempfile.gettempdir()) / "data-gym-cache"))))
    cache_file = cache / "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
    if not cache_file.is_file():
        raise ValueError("Local cl100k tokenizer cache is missing; no implicit download allowed.")
    (out / "sources/tokenizer-cache").mkdir(parents=True)
    shutil.copy2(cache_file, out / "sources/tokenizer-cache" / cache_file.name)
    limits = {**DEFAULT_LIMITS, "max_cost_usd": float(max_cost_usd)}
    versions = {}
    for name in ("openai", "httpx", "pydantic", "pydantic-settings", "numpy", "tiktoken", "json-repair"):
        versions[name] = importlib.metadata.version(name)
    git_info = {}
    for label, repo in (("Jity", root), ("jity-eval", evaluator.parent)):
        git_info[label] = {}
        for field, args in (("head", ["rev-parse", "HEAD"]), ("status", ["status", "--short"])):
            r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
            git_info[label][field] = r.stdout.strip() if r.returncode == 0 else "unborn/unavailable"
    manifest = {"schema_version": 1, "kind": "jity_full_game_capture", "created_at": now(),
                "approval": approval, "limits": limits, "prices": PRICES,
                "price_source": "https://api-docs.deepseek.com/quick_start/pricing/", "pricing_checked_date": "2026-11-06",
                "billing_policy": "Peak cache-miss rates; reserve before each actual HTTP attempt; unknown usage keeps reservation. Unpriced embeddings count against agreed attempt limits.",
                "jity_original_root": str(root), "versions": versions, "python": sys.version,
                "git": git_info, "source_hashes": tree_hash(out / "sources"),
                "config": {"llm_model": "deepseek-flash", "llm_base_url": "https://api.deepseek.com",
                           "campaign_filename": "default_campaign.json", "max_retries": 2,
                           "thinking": "disabled", "max_turns_per_campaign": 50},
                "games": deepcopy(GAME_SPECS), "strict_replay": "Exact raw HTTP responses through original Jity parser and full generate pipeline.",
                "exclusions": ["No paid player model", "No three-arm real-model probe evaluation", "No claim of long-term memory ability", "No git commit/push/merge"],
                "normalization": "Database wall-clock/latency metadata only; full gameplay state, memory, output and progress must match."}
    atomic_json(out / "manifest.json", manifest)
    atomic_json(out / "manifest.sha256.json", {"sha256": digest(manifest)})
    for spec in manifest["games"]:
        game_dir = out / spec["id"]
        game_dir.mkdir()
        atomic_json(game_dir / "game.json", {**spec, "status": "pending", "turns": 0,
                                             "game_over": False, "ending": None, "errors": []})
    launcher = out / "replay.sh"
    launcher.write_text('#!/bin/sh\nset -eu\nCAPTURE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)\ncd "$CAPTURE_DIR"\nPYTHONPATH="$CAPTURE_DIR/sources/evaluator" PYTHONDONTWRITEBYTECODE=1 exec ' + sys.executable + ' -m jity_eval capture replay "$CAPTURE_DIR" "$@"\n', encoding="utf-8")
    launcher.chmod(0o755)
    refresh_summary(out)
    return out


def verify_dataset(dataset_dir):
    out = Path(dataset_dir).resolve()
    manifest = read_json(out / "manifest.json")
    if digest(manifest) != read_json(out / "manifest.sha256.json")["sha256"]:
        raise ValueError("Frozen manifest changed.")
    if tree_hash(out / "sources") != manifest["source_hashes"]:
        raise ValueError("Frozen source/config/prompt/tokenizer resources changed.")
    # A changed working tree cannot silently change the evaluator for this corpus.
    frozen_eval = {k.removeprefix("evaluator/jity_eval/"): v for k, v in manifest["source_hashes"].items() if k.startswith("evaluator/jity_eval/")}
    if tree_hash(Path(__file__).resolve().parents[1]) != frozen_eval:
        raise ValueError("Evaluator code changed. Run with PYTHONPATH=<dataset>/sources/evaluator to use the frozen version.")
    return manifest


def refresh_summary(dataset_dir):
    from .report import render_capture_report
    out = Path(dataset_dir)
    manifest = read_json(out / "manifest.json")
    games = []
    for spec in manifest["games"]:
        path = out / spec["id"] / "game.json"
        game = read_json(path) if path.exists() else {**spec, "status": "pending"}
        game["errors"] = [*game.get("errors", []), *game.get("api_anomalies", []), *game.get("runtime_warnings", [])]
        games.append({**game, "path": spec["id"]})
    budget_path = out / "budget.sqlite3"
    budget = {"limits": manifest["limits"]}
    if budget_path.exists():
        from .journal import BudgetLedger
        ledger = BudgetLedger(budget_path, manifest["limits"], manifest["prices"])
        budget.update(ledger.stats())
        ledger.close()
    completed = sum(g.get("kind") == "game" and g.get("status") == "completed" and g.get("game_over") and bool(g.get("ending")) and g.get("replay", {}).get("status") == "passed" and g["replay"].get("all_calls_consumed") for g in games)
    summary = {"kind": "jity_full_game_capture", "updated_at": now(), "games": games, "budget": budget,
               "completed_games": completed, "requested_games": 4,
               "status": "complete" if completed == 4 else "incomplete",
               "limitations": ["Four fixed recordings are regression fixtures, not evidence that long-term memory is solved.",
                               "Original game answers are not new answers for three memory-ablation groups.",
                               "A turn/budget stop without a legitimate ending remains incomplete."]}
    atomic_json(out / "summary.json", summary)
    render_capture_report(out)
    return summary


def _credentials(root):
    # Read the one allowed credential only into memory, after confirmed budget.
    from dotenv import dotenv_values
    values = dotenv_values(Path(root) / "backend/.env")
    key = os.environ.get("DEEPSEEK_API_KEY") or values.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("Configured DeepSeek credential is unavailable.")
    return key


def _update_game(out, spec, **fields):
    path = out / spec["id"] / "game.json"
    data = read_json(path)
    data.update(fields)
    atomic_json(path, data)
    refresh_summary(out)
    return data


def _call_summary(journal, budget=None, game_id=None):
    stats = journal.stats()
    records = journal.records()
    models = {}
    for row in records:
        body = row.get("request", {}).get("body", {})
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except ValueError:
                body = {}
        model = body.get("model", "unknown") if isinstance(body, dict) else "unknown"
        models[model] = models.get(model, 0) + 1
    result = {"calls_by_purpose": stats.get("purposes", {}), "calls_by_model": models,
            "attempts": stats.get("attempts", 0), "call_statuses": stats.get("statuses", {}),
            "retries": stats.get("repeated_request_attempts", 0),
            "usage": {"input_tokens": stats.get("input_tokens", 0),
                      "output_tokens": stats.get("output_tokens", 0),
                      "total_tokens": stats.get("total_tokens", 0),
                      "unknown_calls": stats.get("unknown_usage", 0)}}
    if budget is not None:
        costs = budget.stats(game_id=game_id)
        result["cost"] = {"known_usd": None, "estimated_usd": costs.get("known_usage_cost_usd", 0),
                          "reserved_usd": costs.get("cost_usd", 0) - costs.get("known_usage_cost_usd", 0),
                          "unpriced_attempts": costs.get("unpriced_attempts", 0),
                          "basis": "Published peak cache-miss rates, not provider invoice; unpriced embeddings excluded and disclosed."}
    result["api_anomalies"] = [
        {"sequence": row["sequence"], "turn": row["context"].get("turn"), "purpose": row["context"].get("purpose"),
         "status_code": (row.get("response") or {}).get("status_code"), "capture_status": row["status"], "error": row.get("error"),
         "note": "Recorded provider attempt; embedding unavailability may trigger Jity's existing hash fallback."}
        for row in records if row["status"] != "complete" or (row.get("response") or {}).get("status_code", 0) >= 400]
    events = journal.events()
    result["runtime_warnings"] = [event["payload"] for event in events if event["kind"] in ("runtime_warning", "story_parse_failure")]
    logical_parse_retries = {}
    for event in events:
        if event["kind"] != "known_parse_retry":
            continue
        payload = event["payload"]
        key = (payload.get("game_id"), payload.get("turn"), payload.get("retry_index"), payload.get("payload_sha256"))
        logical_parse_retries[key] = payload
    # Prefix reconstruction can observe an old retry again without another API
    # request. Count the logical retry once; HTTP accounting remains separate.
    result["known_parse_retries"] = list(logical_parse_retries.values())
    result["response_models"] = sorted({r["response"]["model"] for r in records if (r.get("response") or {}).get("model")})
    return result


async def execute_game(out, spec, *, replay=False, api_key=None, upstream=None):
    from .journal import CallJournal, BudgetLedger, CaptureBoundaryError
    from .transport import CaptureTransport, capture_scope
    from .runtime import JityRuntime
    from .recovery import install_adapter
    from .clocks import install_clock_adapter
    from ..replay.sandbox import replay_sandbox
    out = Path(out).resolve()
    manifest = verify_dataset(out)
    install_adapter(runtime_class=JityRuntime, transport_class=CaptureTransport)
    install_clock_adapter(runtime_class=JityRuntime)
    game_dir = out / spec["id"]
    existing = read_json(game_dir / "game.json")
    scratch_parent = game_dir / ("replays" if replay else "executions")
    scratch_parent.mkdir(exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="run-", dir=scratch_parent))
    source_journal = game_dir / "calls.sqlite3"
    if replay:
        if not source_journal.exists():
            raise ValueError("No raw call journal to replay.")
        import sqlite3
        with sqlite3.connect(source_journal) as source, sqlite3.connect(scratch / "calls.sqlite3") as destination:
            source.backup(destination)
        journal = CallJournal(scratch / "calls.sqlite3")
        budget = None
    else:
        journal = CallJournal(source_journal)
        budget = BudgetLedger(out / "budget.sqlite3", manifest["limits"], manifest["prices"])
    import httpx
    transport = CaptureTransport(journal, upstream=None if replay else (upstream or httpx.AsyncHTTPTransport(retries=0)), budget=budget, mode="replay" if replay else "record", recover=not replay, allowed_hosts=["api.deepseek.com"])
    frozen_root = out / "sources/Jity"
    config = {**manifest["config"], "session_id": spec["id"], "seed": spec["seed"],
              "game_id": spec["id"], "tokenizer_cache": str(out / "sources/tokenizer-cache"),
              "message_clock_path": str(game_dir / "message-clocks.json")}
    traces = []
    def event_sink(kind, payload):
        if not replay:
            journal.event(kind, payload)
        traces.append({"kind": kind, "payload": payload})
    runtime = None
    checkpoints, history = [], []
    replay_result = {"status": "running", "network_attempts": 0, "calls_replayed": 0,
                     "key_state_match": False, "ending_match": False, "reload_match": False, "errors": []}
    error = None
    from .safety import capture_network_guard
    guard = replay_sandbox(frozen_root, scratch) if replay else capture_network_guard()
    guard.__enter__()
    try:
        runtime = JityRuntime(frozen_root, scratch, config=config, transport=transport,
                              api_key=api_key or "offline-replay-only", event_sink=event_sink)
        with nullcontext():
            with capture_scope(game_id=spec["id"], operation_id=spec["id"] + ":boot", turn=0, timeline_node=None):
                initial = await runtime.start()
            initial_path = game_dir / "initial.json"
            if initial_path.exists():
                if read_json(initial_path) != initial:
                    raise ValueError("Initial runtime checkpoint differs from recorded initial state.")
            elif replay:
                raise ValueError("Missing initial state evidence.")
            else:
                atomic_json(initial_path, initial)
                runtime.backup(game_dir / "initial.sqlite3")
            checkpoint = initial
            recorded_paths = sorted((game_dir / "checkpoints").glob("turn-*.json"))
            recorded_turns = len(recorded_paths)
            if any(p.name != "turn-%04d.json" % (i + 1) for i, p in enumerate(recorded_paths)):
                raise ValueError("Non-contiguous committed checkpoints")
            max_turn = recorded_turns if replay else spec["turn_limit"]
            for turn in range(1, max_turn + 1):
                intent_path = game_dir / "intents" / ("turn-%04d.json" % turn)
                checkpoint_path = game_dir / "checkpoints" / ("turn-%04d.json" % turn)
                before = deepcopy(checkpoint)
                if intent_path.exists():
                    intent = read_json(intent_path)
                    if intent["before_sha256"] != digest(before):
                        raise ValueError("Pre-action state mismatch at turn %d" % turn)
                elif replay:
                    raise ValueError("Missing durable action intention at turn %d" % turn)
                else:
                    selection = choose(before, spec["strategy"], spec["seed"], turn, history)
                    request = await runtime.prepare(selection["action"], selection["option_index"], selection["roll"])
                    intent = {"turn": turn, "selection": selection, "request": request,
                              "before_sha256": digest(before), "created_at": now()}
                    atomic_json(intent_path, intent)
                trace_start = len(traces)
                with capture_scope(game_id=spec["id"], operation_id=spec["id"] + ":turn-%d" % turn,
                                   turn=turn, timeline_node=before.get("head")):
                    response = await runtime.generate(intent["request"])
                transport.raise_if_failed()
                checkpoint = runtime.checkpoint()
                if checkpoint_path.exists():
                    expected = read_json(checkpoint_path)
                    if checkpoint != expected:
                        atomic_json(scratch / ("mismatch-%04d.json" % turn), {"recorded": expected, "recomputed": checkpoint})
                        raise ValueError("Full key-state/output/memory/progress mismatch at turn %d" % turn)
                elif replay:
                    raise ValueError("Missing committed checkpoint at turn %d" % turn)
                else:
                    atomic_json(checkpoint_path, checkpoint)
                    atomic_json(game_dir / "traces" / ("turn-%04d.json" % turn),
                                {"intent": intent, "before": before, "response": response,
                                 "after": checkpoint, "events": traces[trace_start:]})
                    backup_path = scratch / ("committed-%04d.sqlite3" % turn)
                    runtime.backup(backup_path)
                    os.replace(backup_path, game_dir / "runtime.sqlite3")
                    _update_game(out, spec, status="recording", turns=turn,
                                 game_over=bool((checkpoint.get("output") or {}).get("game_over")),
                                 ending=(checkpoint.get("output") or {}).get("game_over_reason"),
                                 **_call_summary(journal, budget, spec["id"]))
                    print(json.dumps({"game": spec["id"], "turn": turn, "status": "committed"}, ensure_ascii=False), flush=True)
                checkpoints.append(checkpoint)
                history.append(intent["request"]["player_action"])
                if (checkpoint.get("output") or {}).get("game_over"):
                    break
            transport.assert_consumed()
            before_reload = runtime.checkpoint()
            with capture_scope(game_id=spec["id"], operation_id=spec["id"] + ":reload", turn=len(checkpoints), timeline_node=before_reload.get("head")):
                after_reload = await runtime.reload()
            if before_reload != after_reload:
                atomic_json(scratch / "reload-mismatch.json", {"before": before_reload, "after": after_reload})
                raise ValueError("Reload differs from committed checkpoint.")
            transport.assert_consumed()
            if replay:
                replay_result.update(status="passed", key_state_match=True, ending_match=True, reload_match=True,
                                     calls_replayed=len(journal.records()), turns=len(checkpoints), all_calls_consumed=True)
            else:
                is_over = bool((checkpoint.get("output") or {}).get("game_over"))
                status = "completed" if is_over else "smoke_recorded" if spec["kind"] == "smoke" else "incomplete_turn_limit"
                _update_game(out, spec, status=status, turns=len(checkpoints), game_over=is_over,
                             ending=(checkpoint.get("output") or {}).get("game_over_reason"),
                             coverage=coverage(checkpoints, journal.records()), reload_match=True,
                             **_call_summary(journal, budget, spec["id"]))
                atomic_json(game_dir / "calls.json", journal.records())
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            error = {"type": type(exc).__name__, "message": "Interrupted; durable intentions and raw responses retained."}
        else:
            # Boundary implementations must redact upstream errors; avoid traceback locals/credentials.
            error = {"type": type(exc).__name__, "message": str(exc).replace(api_key, "[REDACTED]") if api_key else str(exc)}
        if replay:
            replay_result.update(status="failed", errors=[error])
        else:
            prior = read_json(game_dir / "game.json")
            _update_game(out, spec, status="incomplete_error", errors=[*prior.get("errors", []), error], **_call_summary(journal, budget, spec["id"]))
            atomic_json(game_dir / "calls.json", journal.records())
    finally:
        try:
            if runtime is not None:
                await runtime.close()
        finally:
            guard.__exit__(None, None, None)
        journal.close()
        if budget is not None:
            budget.close()
    if replay:
        atomic_json(scratch / "result.json", replay_result)
        replay_result["report_path"] = str((scratch / "result.json").relative_to(out))
        latest = checkpoints[-1] if checkpoints else {}
        if replay_result["status"] == "passed":
            is_over = bool((latest.get("output") or {}).get("game_over"))
            _update_game(out, spec, replay=replay_result, turns=len(checkpoints), game_over=is_over,
                         ending=(latest.get("output") or {}).get("game_over_reason"),
                         status="completed" if is_over else "smoke_recorded" if spec["kind"] == "smoke" else "incomplete_turn_limit",
                         coverage=coverage(checkpoints, read_json(game_dir / "calls.json") if (game_dir / "calls.json").exists() else []))
        else:
            _update_game(out, spec, replay=replay_result)
        return replay_result
    if error:
        raise RuntimeError(error["type"] + ": " + error["message"])
    return read_json(game_dir / "game.json")


def replay_game_subprocess(out, game_id):
    out = Path(out).resolve()
    env = {**os.environ, "PYTHONPATH": str(out / "sources/evaluator"), "PYTHONDONTWRITEBYTECODE": "1"}
    # Strict subprocess never needs or inherits credential environment variables.
    env = {k: v for k, v in env.items() if not any(s in k.upper() for s in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))}
    result = subprocess.run([sys.executable, "-m", "jity_eval", "capture", "replay", str(out), "--game", game_id, "--worker"],
                            env=env, cwd=out, check=False)
    if result.returncode:
        raise RuntimeError("Strict offline replay failed for " + game_id)
    return read_json(out / game_id / "game.json")["replay"]


def summary_evidence(out):
    """Require a complete successful raw call AND an adopted nonempty summary."""
    from .journal import CallJournal
    out = Path(out)
    path = out / "smoke/calls.sqlite3"
    if not path.exists():
        return False
    journal = CallJournal(path)
    try:
        calls = journal.records()
    finally:
        journal.close()
    success = any(c["context"].get("purpose") == "memory_nsb_summary" and c["status"] == "complete"
                  and 200 <= (c.get("response") or {}).get("status_code", 0) < 300
                  and c["response"].get("complete")
                  and "length" not in c["response"].get("finish_reasons", []) for c in calls)
    snapshots = sorted((out / "smoke/checkpoints").glob("turn-*.json"))
    adopted = any(any(s.get("summary", "").strip() for level in ("level1", "level2", "level3")
                      for s in (read_json(path).get("state", {}).get("_memory_controller", {}).get("nsb", {}).get(level) or []))
                  for path in snapshots)
    return success and adopted


def collect(dataset_dir, *, smoke_only=False):
    out = Path(dataset_dir).resolve()
    manifest = verify_dataset(out)
    with run_lock(out):
        api_key = _credentials(manifest["jity_original_root"])
        for spec in manifest["games"]:
            if spec["kind"] == "game":
                smoke = read_json(out / "smoke/game.json")
                if smoke.get("replay", {}).get("status") != "passed" or not summary_evidence(out):
                    raise ValueError("Paid full games are gated on summary-covered smoke and strict offline replay.")
                if smoke_only:
                    break
            current = read_json(out / spec["id"] / "game.json")
            if current.get("replay", {}).get("status") == "passed" and (current.get("game_over") or spec["kind"] == "smoke"):
                if spec["kind"] == "smoke":
                    _update_game(out, spec, summary_covered=summary_evidence(out))
                continue
            if current.get("status") not in {"completed", "smoke_recorded"}:
                asyncio.run(execute_game(out, spec, api_key=api_key))
            replay_game_subprocess(out, spec["id"])
            if spec["kind"] == "smoke":
                found = summary_evidence(out)
                _update_game(out, spec, summary_covered=found)
                if not found:
                    raise ValueError("Smoke did not cover an adopted real summary; full collection is blocked.")
        return refresh_summary(out)
