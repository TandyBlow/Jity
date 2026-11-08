"""Tests for runner_guards: the failures the owner found in v3 and in v1 of the
guard itself.

Each test is written against the failure, not the implementation:
- a re-pointed model tag must stop the batch before any call;
- the prompt archived for an attempt must equal the prompt in the actual HTTP
  request body (this is the exact v3 bug: archived intervention, sent original);
- a retry must be exactly base + labelled feedback, never a prefix match (v1 of
  the guard accepted any suffix);
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
def retry_must_equal_its_archived_text():
    base = "要求：新行\n正文："
    retry = g.compose_retry(base, "移动没写")
    assert g.check_prompt(retry, retry, 2)["mode"] == "exact"
    # v1 of the guard accepted this: right prefix, junk suffix
    for bad in (retry + "多余的尾巴", base, base + "\n上一轮的问题：别的\n"):
        try:
            g.check_prompt(retry, bad, 2)
        except g.GuardError as exc:
            assert exc.code == "prompt-differs-from-record", (bad, exc.code)
        else:
            raise AssertionError(f"non-archived retry prompt accepted: {bad!r}")


@case
def retry_composition_is_exact():
    base = "要求：新行\n正文："
    feedback = "移动没写起点"
    retry = g.compose_retry(base, feedback)
    assert retry == base + "\n上一轮的问题：" + feedback + "\n"
    body = {"prompt": retry, "stream": False, "options": {"num_predict": 384}}
    assert g.check_retry_request(retry, base, feedback, body)["sha256"] == \
        g.check_prompt(retry, retry)["sha256"]
    for wrong in ({"prompt": base + "\n上一轮的问题：" + feedback + "\n错"} ,
                  {"prompt": retry, "stream": True}):
        try:
            g.check_retry_request(retry, base, feedback, wrong)
        except g.GuardError as exc:
            assert exc.code in ("prompt-differs-from-record", "request-streamed")
        else:
            raise AssertionError(f"bad retry request accepted: {wrong}")
    for bad_feedback in ("", "   ", feedback + " plus"):
        try:
            g.check_retry_request(retry, base, bad_feedback,
                                  {"prompt": retry, "stream": False})
        except g.GuardError as exc:
            assert exc.code in ("feedback-empty", "prompt-differs-from-record")
        else:
            raise AssertionError(f"feedback mismatch accepted: {bad_feedback!r}")


@case
def http_body_is_verified():
    rec = "要求：新行\n正文："
    ok = {"prompt": rec, "stream": False}
    assert g.check_http_request(rec, ok)["sha256"] ==         g.check_prompt(rec, rec)["sha256"]
    for bad in ({"stream": False}, {"prompt": rec + "x", "stream": False},
                {"prompt": rec, "stream": True}, None):
        try:
            g.check_http_request(rec, bad)
        except g.GuardError as exc:
            assert exc.code in ("request-shape-invalid", "request-prompt-missing",
                                "prompt-differs-from-record", "request-streamed")
        else:
            raise AssertionError(f"bad request body accepted: {bad}")


@case
def missing_finish_reason_is_an_error():
    assert g.finish_reason({"done_reason": "stop"}) == "stop"
    assert g.finish_reason({"done_reason": "load"}) == "load"
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
