"""HTTP helpers and scenario API calls."""

import argparse
import json
import random
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from auto_play_lib.config import DEFAULT_API_BASE_URL, DEFAULT_CONSTRAINTS, DEFAULT_MODEL, DEFAULT_STORY_STYLE


class APIError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def create_session(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": args.model}
    if getattr(args, "campaign", None):
        payload.update({
            "campaign_filename": args.campaign,
            "arc_index": 0,
            "session_index": 0,
            "slot_name": "default",
        })
    return api_post(args.api_base_url, "/sessions", payload, args.timeout)


def prepare_generation(args: argparse.Namespace, session_id: str, action: str) -> dict[str, Any]:
    """Bind one die to one timeline head; retries reuse this exact payload."""
    session = api_get(args.api_base_url, f"/sessions/{session_id}", args.timeout)
    head = session.get("active_turn_id")
    preview = api_post(args.api_base_url, f"/sessions/{session_id}/check", {
        "player_action": action, "timeline_node_id": head,
    }, args.timeout)
    payload: dict[str, Any] = {
        "player_action": action, "timeline_node_id": head,
        "model": args.model, "style": args.style, "constraints": args.constraints,
    }
    if preview.get("option_index") is not None:
        payload["option_index"] = preview["option_index"]
    if preview.get("check"):
        seed = f"{getattr(args, 'seed', 0)}:{session.get('state', {}).get('turn', 0)}:{action}"
        submission = {"roll": random.Random(seed).randint(1, 20)}
        if preview.get("option_index") is not None:
            submission["option_index"] = preview["option_index"]
        payload["action_check"] = submission
    return payload


def generate_scene(args: argparse.Namespace, session_id: str, action: str) -> dict[str, Any]:
    payload = prepare_generation(args, session_id, action)
    return api_post(args.api_base_url, f"/sessions/{session_id}/generate", payload, args.timeout)


def generate_scene_with_retries(args: argparse.Namespace, session_id: str, action: str) -> dict[str, Any]:
    attempts = max(0, args.retries) + 1
    last_error: APIError | None = None
    payload = None
    for attempt in range(1, attempts + 1):
        try:
            if payload is None:
                payload = prepare_generation(args, session_id, action)
            return api_post(args.api_base_url, f"/sessions/{session_id}/generate", payload, args.timeout)
        except APIError as exc:
            last_error = exc
            # A stale head may mean the previous timed-out request committed.
            # Never reinterpret it as a fresh turn or roll another die.
            if exc.status_code in {404, 409, 422} or attempt >= attempts:
                break
            wait_seconds = min(2 * attempt, 8)
            print(f"  请求失败，{wait_seconds}s 后重试 {attempt}/{attempts - 1}: {exc}", file=sys.stderr)
            time.sleep(wait_seconds)
    raise last_error or APIError("unknown generate error")


def api_get(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    request = Request(f"{base_url.rstrip('/')}{path}", method="GET")
    return send_request(request, timeout)


def api_post(base_url: str, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return send_request(request, timeout)


def send_request(request: Request, timeout: float) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
            detail = payload.get("detail") or body
        except json.JSONDecodeError:
            detail = body
        raise APIError(f"HTTP {exc.code}: {detail}", status_code=exc.code) from exc
    except URLError as exc:
        raise APIError(str(exc.reason)) from exc
    except TimeoutError as exc:
        raise APIError("request timed out") from exc
    except json.JSONDecodeError as exc:
        raise APIError(f"invalid JSON response: {exc}") from exc
