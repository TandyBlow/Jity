"""Guards a real-model batch runner must pass BEFORE it sends a prompt.

Why this exists (owner review of 2026-11-08, both points from the archived v3
run):

1. The v3 runner checked the registration, sample and judge hashes but never
   re-read the live Ollama model digest right before inference. A registration
   can be days old and the tag can be re-pointed, so the batch could silently
   run a different model than the one it names.
2. The first v3 attempt archived the intervened prompt but sent the original
   one. Nothing in the code compared "what is recorded" with "what is sent", so
   the mismatch survived until the token counts gave it away.

The frozen `real_batch_v3.py` is left untouched: it is the runner the v3 archive
is pinned to. The next runner must import this module and call
`preflight()` once before the first call, then `check_prompt()` on every attempt.

`finish_reason()` also refuses to guess: a missing `done_reason` is an error,
not `eos`. Defaulting to a normal stop is how a truncated call can be scored as
complete.

Usage as a standalone check (no model call, safe to run any time):

    python -X utf8 runner_guards.py fixtures/batch-v3.json
"""

import hashlib
import json
import pathlib
import urllib.request


class GuardError(Exception):
    def __init__(self, code, detail=None):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def http_tags(endpoint="http://127.0.0.1:11434/api/tags", timeout=10):
    with urllib.request.urlopen(endpoint, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_model_digest(registration, fetch_tags=http_tags):
    """The live tag must be the registered one, byte for byte."""
    want = registration["model"]["digest"]
    name = registration["model"]["name"]
    tags = fetch_tags()
    got = [m for m in tags.get("models", []) if m.get("name") == name]
    if not got:
        raise GuardError("model-absent", name)
    live = got[0].get("digest")
    if live != want:
        raise GuardError("model-digest-changed", f"{name}: registered {want}, "
                                                 f"live {live}")
    return {"name": name, "digest": live,
            "parameterSize": got[0].get("details", {}).get("parameter_size"),
            "quantization": got[0].get("details", {}).get("quantization_level")}


def check_prompt(recorded, prompt, attempt=1):
    """What is sent must be what is archived.

    The first attempt must equal the recorded input. A retry may append feedback,
    so it must START with the recorded input and say so explicitly.
    """
    if not isinstance(recorded, str) or not recorded:
        raise GuardError("prompt-not-recorded", "renderText is empty")
    if not isinstance(prompt, str) or not prompt:
        raise GuardError("prompt-empty", f"attempt {attempt}")
    if prompt == recorded:
        return {"attempt": attempt, "mode": "exact",
                "sha256": _sha256_text(prompt)}
    if attempt == 1:
        raise GuardError("prompt-differs-from-record",
                         f"attempt 1 differs (recorded "
                         f"{_sha256_text(recorded)[:12]}, sent "
                         f"{_sha256_text(prompt)[:12]})")
    if not prompt.startswith(recorded):
        raise GuardError("prompt-retry-not-prefixed",
                         f"attempt {attempt} does not start with the recorded "
                         f"input")
    if "上一轮" not in prompt[len(recorded):]:
        raise GuardError("prompt-retry-unlabelled",
                         f"attempt {attempt} appends text without the retry "
                         f"label")
    return {"attempt": attempt, "mode": "appended-feedback",
            "sha256": _sha256_text(prompt),
            "appendedChars": len(prompt) - len(recorded)}


def finish_reason(data):
    """`done_reason` straight from the port; never invent one."""
    reason = (data or {}).get("done_reason")
    if not isinstance(reason, str) or not reason:
        raise GuardError("finish-reason-missing",
                         "the port returned no done_reason; the call cannot be "
                         "classified as complete or truncated")
    if reason not in ("stop", "length", "eos", "load"):
        raise GuardError("finish-reason-unknown", reason)
    return reason


def preflight(registration, fetch_tags=http_tags):
    """Run before the first call: model identity only, no generation."""
    ident = check_model_digest(registration, fetch_tags)
    return {"model": ident, "checkedAt": "preflight"}


def main() -> int:
    import sys
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    reg = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    try:
        info = preflight(reg)
    except GuardError as exc:
        print(f"PREFLIGHT FAILED {exc.code}: {exc.detail}")
        return 1
    print(f"preflight ok: {info['model']['name']} "
          f"{info['model']['digest'][:12]} "
          f"{info['model']['parameterSize']} "
          f"{info['model']['quantization']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
