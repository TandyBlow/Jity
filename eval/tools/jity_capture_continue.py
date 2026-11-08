#!/usr/bin/env python3
"""Apply one explicitly approved 50 -> 80 submitted-action limit amendment.

This attachment never edits the frozen manifest, source, model settings, game
rules, dice policy, shared budget or retry limits. By default it only validates.
Use --execute only after the original collector has stopped and the user has
approved the separate, hash-bound amendment document.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
import hashlib
import importlib
import json
from pathlib import Path
import re
import sqlite3
import sys


EXPECTED_GAME_IDS = {"game-01", "game-02", "game-03", "game-04"}


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")).hexdigest()


def load_frozen_runner(dataset):
    source = Path(dataset).resolve() / "sources/evaluator"
    expected = source / "jity_eval/capture/runner.py"
    if not expected.is_file():
        raise ValueError("Frozen evaluator runner is missing")
    loaded = sys.modules.get("jity_eval.capture.runner")
    if loaded is not None and Path(loaded.__file__).resolve() != expected:
        raise ValueError("A different evaluator is imported; run this attachment in a fresh process")
    sys.path.insert(0, str(source))
    sys.dont_write_bytecode = True
    runner = importlib.import_module("jity_eval.capture.runner")
    if Path(runner.__file__).resolve() != expected:
        raise ValueError("Refusing to use an evaluator outside this dataset's frozen sources")
    return runner


def validate_amendment(dataset, amendment_path, expected_sha256, manifest):
    out, amendment_path = Path(dataset).resolve(), Path(amendment_path).resolve()
    if out not in amendment_path.parents or (out / "sources") in amendment_path.parents:
        raise ValueError("Approval must be an attachment inside the dataset, outside frozen sources")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Provide the reviewed amendment's lowercase SHA-256")
    if file_sha256(amendment_path) != expected_sha256:
        raise ValueError("Approval document SHA-256 mismatch")
    amendment = read_json(amendment_path)
    checks = {
        "schema_version": 1,
        "kind": "jity_action_limit_amendment",
        "approved": True,
        "approved_by": "user",
        "manifest_sha256": canonical_digest(manifest),
        "original_action_limit": 50,
        "effective_action_limit": 80,
        "campaign_turn_budget": 50,
        "max_retries": 2,
        "limits": manifest["limits"],
        "config_sha256": canonical_digest(manifest["config"]),
        "prices_sha256": canonical_digest(manifest["prices"]),
    }
    for key, expected in checks.items():
        if amendment.get(key) != expected or (isinstance(expected, (int, bool)) and type(amendment.get(key)) is not type(expected)):
            raise ValueError("Approval does not match the permitted amendment: " + key)
    if not isinstance(amendment.get("approval_text"), str) or not amendment["approval_text"].strip():
        raise ValueError("Approval must retain the user's confirmation text and scope")
    approved_at = amendment.get("approved_at")
    if not isinstance(approved_at, str) or datetime.fromisoformat(approved_at.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("Approval timestamp must include its timezone")
    ids = amendment.get("game_ids")
    if not isinstance(ids, list) or len(ids) != 4 or set(ids) != EXPECTED_GAME_IDS:
        raise ValueError("Approval scope must be the existing four formal games")
    if manifest["config"].get("max_turns_per_campaign") != 50 or manifest["config"].get("max_retries") != 2:
        raise ValueError("Frozen game/retry settings are not the approved originals")
    if manifest["limits"].get("max_cost_usd") != 10.0:
        raise ValueError("This amendment preserves the originally approved total USD 10 ceiling")
    formal = [s for s in manifest["games"] if s.get("kind") == "game"]
    if {s["id"] for s in formal} != EXPECTED_GAME_IDS or any(s.get("turn_limit") != 50 for s in formal):
        raise ValueError("Frozen original game action limits must remain 50")
    return amendment


def check_budget_readonly(dataset, manifest):
    """Verify the existing shared ledger; never initialize or reset its limits."""
    path = Path(dataset) / "budget.sqlite3"
    if not path.is_file():
        raise ValueError("Original shared budget ledger is missing")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        config_row = db.execute("SELECT value FROM budget_config WHERE id=1").fetchone()
        stop_row = db.execute("SELECT stop_reason FROM budget_control WHERE id=1").fetchone()
        if config_row is None or json.loads(config_row[0]) != {"limits": manifest["limits"], "prices": manifest["prices"]}:
            raise ValueError("Original budget/pricing configuration differs from the frozen manifest")
        if stop_row is None or stop_row[0]:
            raise ValueError("Shared budget is stopped or its control record is missing")
        totals = db.execute("""SELECT COUNT(*), COALESCE(SUM(COALESCE(input_actual,input_reserved)),0),
            COALESCE(SUM(COALESCE(output_actual,output_reserved)),0),
            COALESCE(SUM(COALESCE(cost_actual,cost_reserved)),0), COALESCE(SUM(unpriced),0),
            COALESCE(SUM(status='reserved'),0) FROM reservations""").fetchone()
    names = ("max_attempts", "max_input_tokens", "max_output_tokens", "max_cost_usd", "max_unpriced_attempts")
    if totals[-1]:
        raise ValueError("Unsettled provider reservations require investigation; continuation refused")
    for key, actual in zip(names, totals):
        if actual > manifest["limits"][key]:
            raise ValueError("Shared budget already exceeds " + key)
    return {"attempts": totals[0], "input_tokens": totals[1], "output_tokens": totals[2],
            "cost_usd": totals[3], "unpriced_attempts": totals[4], "limits": manifest["limits"]}


def eligible_games(dataset, manifest):
    result, skipped = [], []
    for spec in manifest["games"]:
        if spec.get("kind") != "game":
            continue
        game_dir = Path(dataset) / spec["id"]
        game = read_json(game_dir / "game.json")
        if game.get("status") == "completed" and game.get("game_over"):
            skipped.append({"game": spec["id"], "reason": "already_completed"})
            continue
        if game.get("status") != "incomplete_turn_limit":
            raise ValueError("Only incomplete_turn_limit games may continue; %s is %s" % (spec["id"], game.get("status")))
        if game.get("game_over") or game.get("ending"):
            raise ValueError("Inconsistent terminal metadata for " + spec["id"])
        turns = game.get("turns")
        if type(turns) is not int or not 50 <= turns <= 80:
            raise ValueError("Recorded submitted-action count is outside the approved bounds")
        if turns == 80:
            skipped.append({"game": spec["id"], "reason": "approved_action_limit_reached_unfinished"})
            continue
        replay = game.get("replay") or {}
        if replay.get("status") != "passed" or not replay.get("all_calls_consumed") or not replay.get("reload_match"):
            raise ValueError("Existing complete-prefix strict replay must pass before extension: " + spec["id"])
        path = game_dir / "calls.sqlite3"
        if not path.is_file():
            raise ValueError("Raw capture journal missing for " + spec["id"])
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            uncertain = db.execute("SELECT sequence,status FROM calls WHERE status NOT IN ('complete','error') LIMIT 1").fetchone()
            if uncertain:
                raise ValueError("Uncertain/incomplete provider outcome cannot be resumed: %s call %s %s" % (spec["id"], *uncertain))
        if game.get("turn_limit") != 50:
            raise ValueError("Original per-game turn_limit metadata was modified")
        result.append(spec)
    return result, skipped


def continue_dataset(dataset, amendment_path, approval_sha256, *, execute=False, runner=None):
    out = Path(dataset).resolve()
    runner = runner or load_frozen_runner(out)
    # Hold the same process lock as the original collector, including offline
    # checks and per-game replay subprocesses. A live collector blocks us.
    with runner.run_lock(out):
        manifest = runner.verify_dataset(out)
        manifest_bytes = (out / "manifest.json").read_bytes()
        validate_amendment(out, amendment_path, approval_sha256, manifest)
        budget_before = check_budget_readonly(out, manifest)
        smoke = read_json(out / "smoke/game.json")
        if smoke.get("replay", {}).get("status") != "passed" or not runner.summary_evidence(out):
            raise ValueError("Summary-covered smoke and strict replay gate is not satisfied")
        specs, skipped = eligible_games(out, manifest)
        result = {"mode": "execute" if execute else "validation_only", "eligible_games": [s["id"] for s in specs],
                  "skipped": skipped, "original_action_limit": 50, "effective_action_limit": 80,
                  "campaign_turn_budget": 50, "budget_before": budget_before,
                  "amendment_sha256": approval_sha256, "new_real_requests_allowed": bool(execute)}
        if not execute:
            return result
        amendment_relative = str(Path(amendment_path).resolve().relative_to(out))
        api_key = None
        completed = []
        for original_spec in specs:
            # Recheck exact original responses offline before authorizing any
            # new HTTP attempt; no checkpoint acts as a model-response source.
            runner.replay_game_subprocess(out, original_spec["id"])
            current_specs, _ = eligible_games(out, manifest)
            if original_spec["id"] not in {s["id"] for s in current_specs}:
                raise ValueError("Game eligibility changed during preflight replay")
            check_budget_readonly(out, manifest)
            runner._update_game(out, original_spec, original_turn_limit=50, effective_action_limit=80,
                                amendment_path=amendment_relative, amendment_sha256=approval_sha256,
                                continuation_helper_sha256=file_sha256(__file__))
            if api_key is None:
                api_key = runner._credentials(manifest["jity_original_root"])
            # Only the external loop's submitted-action cap changes. Frozen
            # execute_game still takes model/game/budget settings from manifest.
            amended_spec = {**original_spec, "turn_limit": 80}
            asyncio.run(runner.execute_game(out, amended_spec, api_key=api_key))
            runner.replay_game_subprocess(out, original_spec["id"])
            current = read_json(out / original_spec["id"] / "game.json")
            if current.get("turn_limit") != 50 or current.get("original_turn_limit") != 50 or current.get("effective_action_limit") != 80:
                raise ValueError("Original/effective action-limit audit metadata was not preserved")
            if (out / "manifest.json").read_bytes() != manifest_bytes:
                raise ValueError("Frozen manifest changed during continuation")
            runner.verify_dataset(out)
            check_budget_readonly(out, manifest)
            completed.append({"game": original_spec["id"], "status": current["status"],
                              "turns": current["turns"], "game_over": current.get("game_over"),
                              "replay": current.get("replay", {}).get("status")})
        result["games"] = completed
        result["summary"] = runner.refresh_summary(out)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--execute", action="store_true", help="After approval and original collection stops, allow new requests under the existing total budget")
    args = parser.parse_args(argv)
    try:
        result = continue_dataset(args.dataset, args.approval, args.approval_sha256, execute=args.execute)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except BaseException as exc:
        # Never include exception locals or credential-bearing tracebacks.
        if isinstance(exc, KeyboardInterrupt):
            print("Continuation interrupted; existing raw records and intent journal retained.", file=sys.stderr)
            return 130
        detail = ": " + str(exc) if isinstance(exc, (ValueError, FileNotFoundError)) else "; inspect the per-game error and raw-call journal"
        print("Continuation refused/stopped: %s%s" % (type(exc).__name__, detail), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
