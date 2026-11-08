"""Tests for runner_guards: the two failures the owner found in v3.

Each test is written against the failure, not against the implementation:
- a re-pointed model tag must stop the batch before any call;
- a prompt that differs from the archived text must stop the batch (this is the
  exact v3 bug: archived intervention, sent original);
- a missing done_reason must not be read as a normal stop.

Run: python -X utf8 test_runner_guards.py
"""

import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import runner_guards as g  # noqa: E402

REG = json.loads((HERE / "fixtures" / "batch-v3.json")
                 .read_text(encoding="utf-8"))

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def tags_with(digest, name="qwen2.5:7b"):
    def fetch():
        return {"models": [{"name": name, "digest": digest,
                            "details": {"parameter_size": "7.6B",
                                        "quantization_level": "Q4_K_M",
                                        "family": "qwen2"}}]}
    return fetch


@case
def digest_match_passes():
    live = g.check_model_digest(REG, tags_with(REG["model"]["digest"]))
    assert live["digest"] == REG["model"]["digest"]
    assert live["parameterSize"] == "7.6B"


@case
def digest_change_stops():
    try:
        g.check_model_digest(REG, tags_with("0" * 64))
    except g.GuardError as exc:
        assert exc.code == "model-digest-changed"
        assert REG["model"]["digest"] in exc.detail
        return
    raise AssertionError("a re-pointed tag was accepted")


@case
def missing_tag_stops():
    try:
        g.check_model_digest(REG, tags_with(REG["model"]["digest"],
                                            name="other:7b"))
    except g.GuardError as exc:
        assert exc.code == "model-absent"
        return
    raise AssertionError("a missing model was accepted")


@case
def first_prompt_must_equal_record():
    rec = "要求：新行\n正文："
    assert g.check_prompt(rec, rec)["mode"] == "exact"
    # the v3 bug: the recorded text is the intervention, the sent text the old
    # requirement line
    try:
        g.check_prompt(rec, "要求：旧行\n正文：")
    except g.GuardError as exc:
        assert exc.code == "prompt-differs-from-record"
        return
    raise AssertionError("an archive/send mismatch was accepted")


@case
def unrecorded_prompt_stops():
    try:
        g.check_prompt("", "anything")
    except g.GuardError as exc:
        assert exc.code == "prompt-not-recorded"
        return
    raise AssertionError("an unrecorded prompt was accepted")


@case
def retry_must_append_labelled_feedback():
    rec = "要求：新行\n正文："
    ok = g.check_prompt(rec, rec + "\n上一轮的问题：移动没写\n", attempt=2)
    assert ok["mode"] == "appended-feedback"
    for bad, code in ((rec.replace("新行", "旧行"), "prompt-retry-not-prefixed"),
                      (rec + "\n移动没写", "prompt-retry-unlabelled")):
        try:
            g.check_prompt(rec, bad, attempt=2)
        except g.GuardError as exc:
            assert exc.code == code, (exc.code, code)
        else:
            raise AssertionError(f"retry prompt accepted: {code}")


@case
def missing_finish_reason_is_an_error():
    assert g.finish_reason({"done_reason": "stop"}) == "stop"
    for payload in ({}, {"done_reason": None}, {"done_reason": ""}):
        try:
            g.finish_reason(payload)
        except g.GuardError as exc:
            assert exc.code == "finish-reason-missing"
        else:
            raise AssertionError(f"missing done_reason accepted: {payload}")


@case
def unknown_finish_reason_is_an_error():
    try:
        g.finish_reason({"done_reason": "timeout"})
    except g.GuardError as exc:
        assert exc.code == "finish-reason-unknown"
        return
    raise AssertionError("an unknown done_reason was accepted")


def main() -> int:
    bad = 0
    for fn in CASES:
        try:
            fn()
            print(f"ok   {fn.__name__}")
        except AssertionError as exc:
            bad += 1
            print(f"FAIL {fn.__name__}: {exc}")
    print(f"{len(CASES) - bad}/{len(CASES)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
