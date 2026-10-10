#!/usr/bin/env python3
"""Opt-in real-model acceptance against an isolated server/database (12 turns).

Start backend with DATABASE_FILE, CAMPAIGNS_DIR, PROMPT_LOG_DIR and port isolated;
pass the same paths here. Never point this at a user's runtime database.
"""

import argparse
import json
import sqlite3
import subprocess
import time
from pathlib import Path

from campaign_transition_smoke import api


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--campaigns", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", default="deepseek-v4-flash")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    assert args.db.resolve() != (root / "backend/data/jity.sqlite3").resolve()
    assert args.campaigns.resolve() != (root / "backend/data/campaigns").resolve()
    args.campaigns.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    base = json.loads((root / "backend/data/campaigns/budget_five_test_campaign.json").read_text())
    for filename, budget in [("integration-five.json", 5), ("integration-transition.json", 12)]:
        target = args.campaigns / filename
        assert not target.exists(), f"Refusing to overwrite {target}"
        campaign = json.loads(json.dumps(base))
        campaign["max_turns_per_campaign"] = budget
        campaign["arcs"][0]["sessions"][0]["max_turns_per_session"] = 2
        campaign["arcs"][0]["sessions"][1]["max_turns_per_session"] = budget - 2
        target.write_text(json.dumps(campaign, ensure_ascii=False, indent=2))
    evidence = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                "model": args.model, "base": args.base, "runs": [], "passed": False}

    def persist():
        (args.out / "real-model.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2))

    def snapshot(sid, node):
        with sqlite3.connect(args.db) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM story_turns WHERE session_id=? AND id=?", (sid, node)).fetchone()
            return dict(row)

    try:
        for filename, steps in [("integration-five.json", 5), ("integration-transition.json", 6)]:
            created = api(args.base, "POST", "/sessions", {
                "game_name": "isolated-integration-smoke", "campaign_filename": filename,
                "slot_name": "smoke", "model": args.model,
            })
            sid, head = created["session_id"], created["active_turn_id"]
            run = {"campaign": filename, "session_id": sid, "steps": []}
            evidence["runs"].append(run)
            for i in range(steps):
                action = "入场" if i == 0 else "继续"
                result = api(args.base, "POST", f"/sessions/{sid}/generate", {
                    "player_action": action, "slot_name": "smoke", "model": args.model, "timeline_node_id": head,
                })
                head = result["timeline_node_id"]
                node = snapshot(sid, head)
                saved = json.loads(node["state_json"])
                assert result["campaign_progress"]["turns_total"] == i + 1
                assert json.loads(node["campaign_progress_json"])["turns_total"] == i + 1
                assert saved["items"] == result["state"]["items"]
                assert saved["_memory_controller"]["version"]
                assert result["caps"]["items"] is None
                detail = api(args.base, "GET", f"/sessions/{sid}/timeline/{head}")
                if result["source"] == "llm":
                    assert detail["context"]["recorded"] and detail["context"]["prompt_text"]
                result["recorded_context"] = detail["context"]
                run["steps"].append(result)
                persist()
                print(filename, i + 1, result["source"], "ending", result["output"]["game_over"], flush=True)
            assert run["steps"][1]["campaign_progress"]["session_index"] == 1
            assert run["steps"][2]["source"] == "scripted"
            assert "废弃了十年" in json.dumps(run["steps"][2]["state"]["world_facts"], ensure_ascii=False)
            if steps == 5:
                assert result["output"]["game_over"] and result["output"]["options"] == []
                assert json.loads(snapshot(sid, head)["campaign_progress_json"])["fsm_state"] == "campaign_end"
            else:
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    memory = json.loads(snapshot(sid, head)["state_json"])["_memory_controller"]
                    if memory["nsb"]["level1"]:
                        break
                    time.sleep(1)
                assert memory["nsb"]["level1"], "Real background summary did not persist"
                run["summarized_memory"] = memory
                earlier = run["steps"][3]["timeline_node_id"]
                original = snapshot(sid, earlier)
                restored = api(args.base, "POST", f"/sessions/{sid}/timeline/{earlier}/activate")
                assert restored["active_turn_id"] == earlier
                continuation = api(args.base, "POST", f"/sessions/{sid}/generate", {
                    "player_action": "继续", "slot_name": "smoke", "model": args.model, "timeline_node_id": earlier,
                })
                assert continuation["parent_timeline_node_id"] == earlier
                assert continuation["campaign_progress"]["turns_total"] == 5
                assert snapshot(sid, earlier)["state_json"] == original["state_json"]
                run["restored_from"] = earlier
                run["steps"].append(continuation)
                print(filename, "restored and continued", flush=True)
        evidence["passed"] = True
    except Exception as exc:
        evidence["error"] = str(exc)
        raise
    finally:
        persist()


if __name__ == "__main__":
    main()
