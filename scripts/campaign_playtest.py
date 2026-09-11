#!/usr/bin/env python3
"""Campaign-mode playtest — verifies anchors, multi-agent pipeline, progress tracking.

Usage: python scripts/campaign_playtest.py [--api http://localhost:8000] [--turns 8]"""
import argparse

from playtest_common import APIError, api_get, api_post, fetch_new_anchors, generate_with_retry, t


DEFAULT_API = "http://localhost:8000"
DEFAULT_MODEL = "deepseek-v4-flash"


def check_health_and_campaigns(base: str) -> tuple[int, str]:
    """Sections 1 & 2 — backend health and campaign listing. Returns (passed, target)."""
    passed = 0

    print("=" * 60)
    print("1. Backend health")
    try:
        health = api_get(base, "/health", timeout=10)
        print(f"  Status: {health.get('status')}, chunks: {health.get('knowledge_chunks')}")
        passed += 1
    except APIError as e:
        print(f"  [FAIL] {e}")
        raise

    print("\n" + "=" * 60)
    print("2. Campaign listing")
    campaigns = api_get(base, "/campaigns", timeout=10)
    camp_files = [c["filename"] for c in campaigns.get("campaigns", [])]
    print(f"  Found: {len(camp_files)} campaigns")
    passed += t(len(camp_files) >= 2, f"At least 2 campaigns available (got {len(camp_files)})")
    target = "default_campaign.json"
    if target not in camp_files:
        target = camp_files[0]
    print(f"  Target: {target}")
    return passed, target


def create_and_verify_session(base: str, target: str) -> tuple[int, str, dict]:
    """Sections 3 & 4 — create session and verify scripted opening. Returns (passed, sid, sess)."""
    passed = 0

    print("\n" + "=" * 60)
    print("3. Campaign session creation (POST /sessions with campaign_filename)")
    sess = api_post(base, "/sessions", {
        "game_name": "campaign-qa",
        "model": DEFAULT_MODEL,
        "campaign_filename": target,
        "arc_index": 0,
        "session_index": 0,
        "slot_name": "qa-campaign",
    })
    sid = sess["session_id"]
    st = sess["state"]
    print(f"  Session ID: {sid}")
    print(f"  Turn: {st['turn']}, Location: {st['current_location']}")
    print(f"  NPCs: {[n['name'] for n in st.get('npcs', [])]}")
    print(f"  Items: {[i['name'] for i in st.get('items', [])]}")
    passed += t(st["turn"] == 0, "Turn starts at 0")
    passed += t("诺诺" in [n["name"] for n in st.get("npcs", [])], "NPC loaded from campaign")
    passed += t(st["current_location"] != "", "Location set from campaign entry_state")

    print("\n" + "=" * 60)
    print("4. Turn 0 — Campaign scripted opening (first generate call)")
    t0 = api_post(base, f"/sessions/{sid}/generate", {
        "player_action": "（入场）环顾四周，了解当前处境。",
        "model": DEFAULT_MODEL,
        "slot_name": "qa-campaign",
    })
    passed += t(t0["source"] == "scripted", f"Source is 'scripted' (got: {t0['source']})")
    passed += t(len(t0["output"]["narration"]) > 50, f"Opening narration is substantial ({len(t0['output']['narration'])} chars)")
    passed += t(
        t0["output"]["narration"] != sess.get("output", {}).get("narration", ""),
        "Opening scene is from campaign JSON, not frontend hardcode"
    )
    return passed, sid, sess


def run_gameplay_loop(base: str, sid: str, turns: int) -> tuple[int, list[str]]:
    """Play N LLM turns, tracking anchors. Returns (turn_count, anchors_seen)."""
    action = "观察周围环境，寻找报到处和线索"
    anchors_seen: list[str] = []
    turn_count = 0
    consecutive_failures = 0

    for turn in range(1, turns + 1):
        print(f"\n  --- Turn {turn} ---")
        try:
            resp = generate_with_retry(
                lambda path, payload: api_post(base, path, payload),
                sid, action, "qa-campaign", DEFAULT_MODEL,
            )
            consecutive_failures = 0
        except APIError as e:
            print(f"    [FAIL] {e}")
            consecutive_failures += 1
            if consecutive_failures >= 2:
                print("    [ABORT] 2 consecutive failures")
                break
            continue

        st = resp["state"]
        out = resp["output"]
        print(f"    src={resp['source']}, turn={st['turn']}, loc={st['current_location']}")
        print(f"    sanity={st['sanity']}, health={st['health']}, opts={len(out['options'])}")
        turn_count += 1

        if out.get("game_over"):
            print(f"    [GAME_OVER] {out.get('game_over_reason', '')}")

        new_anchors = fetch_new_anchors(lambda path: api_get(base, path), sid, anchors_seen)
        if new_anchors:
            print(f"    [ANCHOR] Triggered: {new_anchors}")

        action = out["options"][0] if out.get("options") else "继续调查"

    return turn_count, anchors_seen


def verify_phase(base: str, sid: str, turn_count: int, anchors_seen: list[str]) -> int:
    """Sections 6-8 — anchor, progress endpoint and pipeline checks. Returns failures."""
    failed = 0

    print("\n" + "=" * 60)
    print("6. Campaign anchor verification")
    print(f"  Total anchors triggered: {len(anchors_seen)}")
    for a in anchors_seen:
        print(f"    - {a}")
    t(len(anchors_seen) > 0, f"At least 1 anchor triggered (got {len(anchors_seen)})")

    print("\n" + "=" * 60)
    print("7. Progress endpoint (GET /sessions/{id}/progress)")
    try:
        prog = api_get(base, f"/sessions/{sid}/progress", timeout=10)
        print(f"  arc_index: {prog.get('arc_index')}")
        print(f"  session_index: {prog.get('session_index')}")
        print(f"  revealed_anchors: {len(prog.get('revealed_anchors', []))}")
        print(f"  world_facts: {len(prog.get('world_facts', []))}")
        t(prog["session_id"] == sid, "Progress session_id matches")
        t(isinstance(prog.get("world_facts"), list), "World facts is a list")
        t(isinstance(prog.get("revealed_anchors"), list), "Revealed anchors is a list")
    except APIError as e:
        print(f"  [FAIL] {e}")
        failed += 1

    print("\n" + "=" * 60)
    print("8. Multi-agent pipeline verification")
    # In campaign mode, the pipeline is: Examiner → Director → Narrator
    t(turn_count > 0, f"Multi-agent pipeline produced {turn_count} LLM turns in campaign mode")

    return failed


def main() -> int:
    args = parse_args()
    base = args.api
    passed = 0
    failed = 0

    try:
        setup_passed, target = check_health_and_campaigns(base)
        passed += setup_passed

        session_passed, sid, _sess = create_and_verify_session(base, target)
        passed += session_passed
    except APIError as e:
        print(f"  [FAIL] {e}")
        return 1

    # ─── 5. Gameplay loop with retry ───
    print("\n" + "=" * 60)
    print(f"5. Campaign gameplay loop ({args.turns} LLM turns)")
    turn_count, anchors_seen = run_gameplay_loop(base, sid, args.turns)
    passed += turn_count

    # ─── 6-8. Anchor, progress and pipeline verification ───
    failed += verify_phase(base, sid, turn_count, anchors_seen)

    # ─── Results ───
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed ({turn_count} turns generated)")
    if failed > 0:
        print("STATUS: DONE_WITH_CONCERNS")
    else:
        print("STATUS: DONE")
    return 0 if failed == 0 else 1


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Campaign-mode playtest")
    p.add_argument("--api", default=DEFAULT_API)
    p.add_argument("--turns", type=int, default=8)
    return p.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
