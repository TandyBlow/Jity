"""HTTP helpers and scenario API calls."""

import argparse
import json
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from auto_play_lib.config import DEFAULT_API_BASE_URL, DEFAULT_CONSTRAINTS, DEFAULT_MODEL, DEFAULT_STORY_STYLE


class APIError(RuntimeError):
    pass


def create_session(args: argparse.Namespace) -> dict[str, Any]:
    return api_post(args.api_base_url, "/sessions", {"model": args.model}, args.timeout)


def generate_scene(args: argparse.Namespace, session_id: str, action: str) -> dict[str, Any]:
    return api_post(
        args.api_base_url,
        f"/sessions/{session_id}/generate",
        {
            "player_action": action,
            "model": args.model,
            "style": args.style,
            "constraints": args.constraints,
        },
        args.timeout,
    )


def generate_scene_with_retries(args: argparse.Namespace, session_id: str, action: str) -> dict[str, Any]:
    attempts = max(0, args.retries) + 1
    last_error: APIError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return generate_scene(args, session_id, action)
        except APIError as exc:
            last_error = exc
            if attempt >= attempts:
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
        raise APIError(f"HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise APIError(str(exc.reason)) from exc
    except TimeoutError as exc:
        raise APIError("request timed out") from exc
    except json.JSONDecodeError as exc:
        raise APIError(f"invalid JSON response: {exc}") from exc

