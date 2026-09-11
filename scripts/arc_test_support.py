"""Support layer for scripts/arc_completion_test.py — API access and retries."""

import json
import time
from urllib.request import Request

from playtest_common import APIError, _send

BASE = "http://127.0.0.1:8000"
MODEL = "deepseek-v4-flash"
SLOT = "arc-test"
MAX_TURNS = 5  # low to trigger fast session advancement
TEMP_CAMPAIGN = "_arc_completion_test.json"


def post(path: str, payload: dict, timeout: float = 180) -> dict:
    req = Request(f"{BASE}{path}", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                  method="POST", headers={"Content-Type": "application/json"})
    return _send(req, timeout)


def get(path: str) -> dict:
    req = Request(f"{BASE}{path}", method="GET")
    return _send(req, 30)


def generate_with_retry(sid: str, action: str, max_retries: int = 4) -> dict:
    last_err = None
    for attempt in range(max_retries):
        try:
            return post(f"/sessions/{sid}/generate", {
                "player_action": action, "model": MODEL, "slot_name": SLOT,
            })
        except APIError as e:
            last_err = e
            if any(str(c) in str(e) for c in ["500", "502", "503"]):
                wait = 2 ** (attempt + 1)
                print(f"      [retry {attempt+1}/{max_retries}, {wait}s] {e}")
                time.sleep(wait)
            else:
                raise
    raise last_err or APIError("exhausted retries")
