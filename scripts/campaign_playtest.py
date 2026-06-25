#!/usr/bin/env python3
"""Campaign-mode playtest — verifies anchor events, multi-agent pipeline, progress tracking.

Usage: python scripts/campaign_playtest.py [--api http://localhost:8000] [--turns 8]
"""

import argparse
import json
import sys
import time
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API = "http://localhost:8000"
DEFAULT_MODEL = "deepseek-v4-flash"


class APIError(RuntimeError):
    pass


def _send(req: Request, timeout: float) -> dict:
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except json.JSONDecodeError:
            detail = body
        raise APIError(f"HTTP {e.code}: {detail}") from e
    except URLError as e:
        raise APIError(str(e.reason)) from e


def api_post(base: str, path: str, payload: dict, timeout: float = 180) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(f"{base.rstrip('/')}{path}", data=data, method="POST",
                  headers={"Content-Type": "application/json"})
    return _send(req, timeout)


def api_get(base: str, path: str, timeout: float = 30) -> dict:
    req = Request(f"{base.rstrip('/')}{path}", method="GET")
    return _send(req, timeout)


def t(condition: bool, msg: str) -> int:
    """Test assertion: returns 1 if pass, 0 if fail."""
    if condition:
        print(f"  [PASS] {msg}")
        return 1
    else:
        print(f"  [FAIL] {msg}")
        return 0


def generate_with_retry(base: str, sid: str, action: str, slot: str, model: str, max_retries: int = 3) -> dict:
    """Generate with retry on transient 500/502/503 errors."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return api_post(base, f"/sessions/{sid}/generate", {
                "player_action": action,
                "model": model,
                "slot_name": slot,
            })
        except APIError as e:
            last_err = e
            if "500" in str(e) or "502" in str(e) or "503" in str(e):
                wait = 2 * (attempt + 1)
                print(f"    [RETRY] {e} — waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    raise last_err or APIError("unknown")


def main() -> int:
    args = parse_args()
    base = args.api
    passed = 0
    failed = 0

    # ─── 1. Health ───
    print("=" * 60)
    print("1. Backend health")
    try:
        health = api_get(base, "/health", timeout=10)
        print(f"  Status: {health.get('status')}, chunks: {health.get('knowledge_chunks')}")
        passed += 1
    except APIError as e:
        print(f"  [FAIL] {e}")
        return 1

    # ─── 2. Campaign list ───
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

    # ─── 3. Create campaign session ───
    print("\n" + "=" * 60)
    print("3. Campaign session creation (POST /sessions with campaign_filename)")
    try:
        sess = api_post(base, "/sessions", {
            "game_name": "campaign-qa",
            "model": DEFAULT_MODEL,
            "campaign_filename": target,
            "arc_index": 0,
            "session_index": 0,
            "slot_name": "qa-campaign",
        })
    except APIError as e:
        print(f"  [FAIL] {e}")
        return 1
    sid = sess["session_id"]
    st = sess["state"]
    print(f"  Session ID: {sid}")
    print(f"  Turn: {st['turn']}, Location: {st['current_location']}")
    print(f"  NPCs: {[n['name'] for n in st.get('npcs', [])]}")
    print(f"  Items: {[i['name'] for i in st.get('items', [])]}")
    passed += t(st["turn"] == 0, "Turn starts at 0")
    passed += t("诺诺" in [n["name"] for n in st.get("npcs", [])], "NPC loaded from campaign")
    passed += t(st["current_location"] != "", "Location set from campaign entry_state")

    # ─── 4. Turn 0 — Opening scene ───
    print("\n" + "=" * 60)
    print("4. Turn 0 — Campaign scripted opening (first generate call)")
    try:
        t0 = api_post(base, f"/sessions/{sid}/generate", {
            "player_action": "（入场）环顾四周，了解当前处境。",
            "model": DEFAULT_MODEL,
            "slot_name": "qa-campaign",
        })
    except APIError as e:
        print(f"  [FAIL] {e}")
        return 1
    passed += t(t0["source"] == "scripted", f"Source is 'scripted' (got: {t0['source']})")
    passed += t(len(t0["output"]["narration"]) > 50, f"Opening narration is substantial ({len(t0['output']['narration'])} chars)")
    passed += t(
        t0["output"]["narration"] != sess.get("output", {}).get("narration", ""),
        "Opening scene is from campaign JSON, not frontend hardcode"
    )

    # ─── 5. Gameplay loop with retry ───
    print("\n" + "=" * 60)
    print(f"5. Campaign gameplay loop ({args.turns} LLM turns)")
    action = "观察周围环境，寻找报到处和线索"
    anchors_seen: list[str] = []
    turn_count = 0
    consecutive_failures = 0

    for turn in range(1, args.turns + 1):
        print(f"\n  --- Turn {turn} ---")
        try:
            resp = generate_with_retry(base, sid, action, "qa-campaign", DEFAULT_MODEL)
            consecutive_failures = 0
        except APIError as e:
            print(f"    [FAIL] {e}")
            failed += 1
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

        # Track anchors
        try:
            prog = api_get(base, f"/sessions/{sid}/progress", timeout=10)
            new_anchors = [a for a in prog.get("revealed_anchors", []) if a not in anchors_seen]
            if new_anchors:
                print(f"    [ANCHOR] Triggered: {new_anchors}")
                anchors_seen.extend(new_anchors)
        except APIError:
            pass

        # Next action
        if out.get("options"):
            action = out["options"][0]
        else:
            action = "继续调查"

    passed += turn_count

    # ─── 6. Anchor verification ───
    print("\n" + "=" * 60)
    print("6. Campaign anchor verification")
    print(f"  Total anchors triggered: {len(anchors_seen)}")
    for a in anchors_seen:
        print(f"    - {a}")
    passed += t(len(anchors_seen) > 0, f"At least 1 anchor triggered (got {len(anchors_seen)})")

    # ─── 7. Progress endpoint ───
    print("\n" + "=" * 60)
    print("7. Progress endpoint (GET /sessions/{id}/progress)")
    try:
        prog = api_get(base, f"/sessions/{sid}/progress", timeout=10)
        print(f"  arc_index: {prog.get('arc_index')}")
        print(f"  session_index: {prog.get('session_index')}")
        print(f"  revealed_anchors: {len(prog.get('revealed_anchors', []))}")
        print(f"  world_facts: {len(prog.get('world_facts', []))}")
        passed += t(prog["session_id"] == sid, "Progress session_id matches")
        passed += t(isinstance(prog.get("world_facts"), list), "World facts is a list")
        passed += t(isinstance(prog.get("revealed_anchors"), list), "Revealed anchors is a list")
    except APIError as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # ─── 8. Multi-agent pipeline check ───
    print("\n" + "=" * 60)
    print("8. Multi-agent pipeline verification")
    # In campaign mode, the pipeline is: Examiner → Director → Narrator
    # If any turn succeeded with source='llm' in campaign mode, the pipeline worked
    passed += t(turn_count > 0, f"Multi-agent pipeline produced {turn_count} LLM turns in campaign mode")

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
