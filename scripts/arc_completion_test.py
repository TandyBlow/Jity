#!/usr/bin/env python3
"""Run through 1 full campaign arc (all sessions) with short max_turns.

Creates a temporary campaign copy with max_turns_per_session=5,
runs through all sessions until arc completion, then cleans up.
"""

import json
from pathlib import Path

from arc_test_support import (
    MAX_TURNS,
    MODEL,
    SLOT,
    TEMP_CAMPAIGN,
    generate_with_retry,
    get,
    post,
)
from playtest_common import APIError


def prepare_campaign() -> Path:
    """Section 1 — write a temp campaign copy with short sessions. Returns tmp path."""
    print("=" * 60)
    print("Preparing test campaign with max_turns_per_session=5")
    campaigns_dir = Path("backend/data/campaigns")
    src = campaigns_dir / "default_campaign.json"
    tmp = campaigns_dir / TEMP_CAMPAIGN
    camp = json.loads(src.read_text(encoding="utf-8"))
    camp["title"] = camp.get("title", "") + " [ARC-TEST]"
    session_count = 0
    for arc in camp["arcs"]:
        for sess in arc["sessions"]:
            sess["max_turns_per_session"] = MAX_TURNS
            session_count += 1
    print(f"  Arc 0 sessions: {len(camp['arcs'][0]['sessions'])} (total: {session_count})")
    print(f"  Arc 0 goal: {camp['arcs'][0]['goal']}")
    for i, sess in enumerate(camp["arcs"][0]["sessions"]):
        print(f"    S{i}: {sess['name']} (max_turns={sess.get('max_turns_per_session')}) - {len(sess['anchor_events'])} anchors")
    tmp.write_text(json.dumps(camp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Written to: {tmp}")
    return tmp


def create_and_open_session() -> str:
    """Sections 2 & 3 — create session at Arc 0/S0 and run the scripted opening. Returns session_id."""
    print("\n" + "=" * 60)
    print("Creating campaign session at Arc 0, Session 0")
    sess = post("/sessions", {
        "game_name": "arc-completion-test",
        "model": MODEL,
        "campaign_filename": TEMP_CAMPAIGN,
        "arc_index": 0, "session_index": 0, "slot_name": SLOT,
    })
    sid = sess["session_id"]
    st = sess["state"]
    print(f"  Session: {sid}")
    print(f"  Arc 0, Session 0 开场: {st['current_location']}")
    print(f"  NPCs: {[n['name'] for n in st.get('npcs', [])]}")

    print("\n--- Turn 0 (opening scene) ---")
    resp = post(f"/sessions/{sid}/generate", {
        "player_action": "（入场）了解当前处境。",
        "model": MODEL, "slot_name": SLOT,
    })
    print(f"  src={resp['source']}, loc={resp['state']['current_location']}")
    assert resp["source"] == "scripted", "Turn 0 must be scripted!"
    return sid


def run_arc_loop(sid: str) -> tuple[int, int, int, list[dict], list[str]]:
    """Section 4 — play until Arc 0 completes. Returns (arc, turns, boundaries, anchors)."""
    print("\n" + "=" * 60)
    print("Running gameplay loop until arc completes...\n")

    action = "观察周围环境，寻找线索"
    total_turns = 0
    current_arc = 0
    current_session = 0
    session_boundaries: list[dict] = []
    anchors_all: list[str] = []
    turn_in_session = 1  # after opening

    while current_arc == 0:  # run until Arc 0 completes
        total_turns += 1
        print(f"[Turn {total_turns}] arc={current_arc} sess={current_session} turn_in_sess={turn_in_session} | {action[:50]}...")

        try:
            resp = generate_with_retry(sid, action)
        except APIError as e:
            print(f"  FAILED after retries: {e}")
            break

        st = resp["state"]
        out = resp["output"]

        # Check progress
        try:
            prog = get(f"/sessions/{sid}/progress")
            new_arc = prog.get("arc_index", 0)
            new_sess = prog.get("session_index", 0)
            new_anchors = [a for a in prog.get("revealed_anchors", []) if a not in anchors_all]

            if new_anchors:
                print(f"  [ANCHOR] {new_anchors}")
                anchors_all.extend(new_anchors)

            if new_sess != current_session:
                print(f"  >>> SESSION ADVANCE: {current_session} -> {new_sess} <<<")
                session_boundaries.append({
                    "turn": total_turns,
                    "from_session": current_session,
                    "to_session": new_sess,
                    "arc": new_arc,
                })
                current_session = new_sess
                turn_in_session = 0

            if new_arc != current_arc:
                print(f"  >>> ARC COMPLETE: arc {current_arc} -> {new_arc} <<<")
                current_arc = new_arc
                break

            current_arc = new_arc
        except APIError:
            pass

        # Status
        print(f"  loc={st['current_location']}, sanity={st['sanity']}, health={st['health']}, opts={len(out['options'])}")

        if out.get("game_over"):
            print(f"  [GAME_OVER] {out.get('game_over_reason', '')}")
            break

        # Next action
        action = out["options"][0] if out.get("options") else "继续调查"
        turn_in_session += 1

    return current_arc, total_turns, session_boundaries, anchors_all


def main() -> int:
    tmp = prepare_campaign()

    try:
        sid = create_and_open_session()
        current_arc, total_turns, session_boundaries, anchors_all = run_arc_loop(sid)
        all_pass = _verify_arc(current_arc, total_turns, session_boundaries, anchors_all, sid)
    finally:
        # ── Cleanup ──
        if tmp.exists():
            tmp.unlink()
            print(f"\n  Cleaned up: {tmp.name}")

    return 0 if all_pass else 1


def _verify_arc(current_arc, total_turns, session_boundaries, anchors_all, sid) -> bool:
    """Section 5 — verify arc completion and print results. Returns True if all checks pass."""
    print("\n" + "=" * 60)
    print("ARC COMPLETION VERIFICATION")

    prog = get(f"/sessions/{sid}/progress")
    print(f"  Final arc_index: {prog.get('arc_index')}")
    print(f"  Final session_index: {prog.get('session_index')}")
    print(f"  Total turns: {total_turns}")
    print(f"  Total anchors: {len(anchors_all)} ({anchors_all})")
    print(f"  Session advances: {len(session_boundaries)}")
    for sb in session_boundaries:
        print(f"    Turn {sb['turn']}: session {sb['from_session']} -> {sb['to_session']}")

    checks = []
    checks.append(("Arc completed (arc_index >= 1)", current_arc >= 1))
    checks.append(("At least 1 session advance", len(session_boundaries) >= 1))
    checks.append(("Anchors triggered across sessions", len(anchors_all) > 0))
    checks.append((f"Reasonable turn count (<= {MAX_TURNS * 3})", total_turns <= MAX_TURNS * 3))

    all_pass = True
    for label, ok in checks:
        mark = "[PASS]" if ok else "[FAIL]"
        if not ok: all_pass = False
        print(f"  {mark} {label}")

    print(f"\n  STATUS: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
    return all_pass


if __name__ == "__main__":
    raise SystemExit(main())
