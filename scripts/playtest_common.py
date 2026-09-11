"""Shared HTTP helpers for playtest scripts (auto_play, campaign_playtest, arc tests)."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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


def generate_with_retry(
    post_fn, sid: str, action: str, slot: str, model: str,
    max_retries: int = 3, base_label: str = "",
) -> dict:
    """Generate with retry on transient 500/502/503 errors.

    ``post_fn(path, payload)`` must return the parsed response dict.
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            return post_fn(f"/sessions/{sid}/generate", {
                "player_action": action,
                "model": model,
                "slot_name": slot,
            })
        except APIError as e:
            last_err = e
            if "500" in str(e) or "502" in str(e) or "503" in str(e):
                wait = 2 * (attempt + 1)
                prefix = f"[{base_label}] " if base_label else ""
                print(f"    {prefix}[RETRY] {e} — waiting {wait}s (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    raise last_err or APIError("unknown")


def fetch_new_anchors(get_fn, sid: str, seen: list[str]) -> list[str]:
    """Fetch /progress and return revealed anchors not yet in *seen* (updated in place)."""
    try:
        prog = get_fn(f"/sessions/{sid}/progress")
        new_anchors = [a for a in prog.get("revealed_anchors", []) if a not in seen]
        if new_anchors:
            seen.extend(new_anchors)
        return new_anchors
    except APIError:
        return []
