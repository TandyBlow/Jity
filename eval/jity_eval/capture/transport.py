"""Exact HTTP-attempt capture/replay, including SDK retries and embeddings.

Use a single transport for all OpenAI-compatible clients. Replay never constructs
an upstream transport. Successful response bytes are persisted before the SDK can
parse them. A partial response or interrupted request is never silently retried.
"""
from __future__ import annotations

import base64
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
import json
import hashlib
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .journal import (BudgetExceeded, CallJournal, CaptureBoundaryError,
                      MissingCapture, UncertainCapture, clean, fingerprint)


_context = ContextVar("jity_capture_context", default={})
network_allowed = ContextVar("jity_capture_network_allowed", default=False)
# asyncio's legacy getaddrinfo executor does not propagate ContextVars. The
# process guard may authorize only this exact hostname while recorded IO runs;
# socket connections still require the task-local network_allowed flag.
network_dns_hosts = Counter()


@contextmanager
def capture_scope(**metadata):
    token = _context.set({**_context.get(), **clean(metadata)})
    try:
        yield
    finally:
        _context.reset(token)


def current_scope():
    return dict(_context.get())


def _b64(value):
    return base64.b64encode(value).decode("ascii")


def _bytes(value):
    return base64.b64decode(value, validate=True)


def _url(value):
    parsed = urlsplit(str(value))
    safe_query = [(k, "[REDACTED]" if any(s in k.lower() for s in ("key", "token", "secret", "signature")) else v)
                  for k, v in parse_qsl(parsed.query, keep_blank_values=True)]
    host = parsed.hostname or ""
    if parsed.port:
        host += ":" + str(parsed.port)
    return urlunsplit((parsed.scheme, host, parsed.path, urlencode(safe_query), ""))


_REQUEST_HEADERS = {"content-type", "accept", "openai-beta", "openai-organization", "openai-project",
                    "x-stainless-retry-count", "x-stainless-read-timeout"}
_RESPONSE_HEADERS = {"content-type", "content-encoding", "content-length", "x-request-id", "request-id",
                     "retry-after", "retry-after-ms", "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
                     "x-ratelimit-reset-requests", "x-ratelimit-limit-tokens", "x-ratelimit-remaining-tokens",
                     "x-ratelimit-reset-tokens", "date"}


def _headers(headers, allowed):
    return [[key, value] for key, value in headers.multi_items() if key.lower() in allowed]


def _secrets(request):
    values = []
    for key, value in request.headers.multi_items():
        if key.lower() in {"authorization", "api-key", "x-api-key"}:
            values.extend([value, value.split(" ", 1)[-1]])
    return tuple(value for value in values if value)


def _protect_bytes(value, secrets):
    for secret in secrets:
        value = value.replace(secret.encode("utf-8"), b"[REDACTED]")
    return value


def _response_metadata(raw, headers, streamed):
    """Extract usage/finish evidence without replacing the raw response bytes."""
    result = {"usage": None, "model": None, "finish_reasons": [], "streamed": streamed,
              "eof_observed": True, "stream_done": None}
    try:
        # httpx decodes compressed transport bytes here, exactly as the SDK will.
        decoded = httpx.Response(200, headers=headers, content=raw).content
        if streamed:
            documents = []
            done = False
            for line in decoded.decode("utf-8").splitlines():
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if value == "[DONE]":
                    done = True
                elif value:
                    documents.append(json.loads(value))
            result["stream_done"] = done
            result["assembled_text"] = "".join(
                str(choice.get("delta", {}).get("content") or "")
                for document in documents for choice in document.get("choices", []))
        else:
            documents = [json.loads(decoded)]
        for document in documents:
            if not isinstance(document, dict):
                continue
            if isinstance(document.get("usage"), dict):
                result["usage"] = document["usage"]
            if document.get("model"):
                result["model"] = document["model"]
            for choice in document.get("choices", []):
                if choice.get("finish_reason") is not None:
                    result["finish_reasons"].append(choice["finish_reason"])
    except (ValueError, UnicodeDecodeError, TypeError, httpx.DecodingError):
        result["body_parseable"] = False
    else:
        result["body_parseable"] = True
    return result


class CaptureTransport(httpx.AsyncBaseTransport):
    def __init__(self, journal: CallJournal, upstream=None, budget=None,
                 mode="record", recover=False, allowed_hosts=None):
        if mode not in {"record", "replay"}:
            raise ValueError("mode must be record or replay")
        if mode == "replay" and upstream is not None:
            raise ValueError("Replay must not have an upstream transport")
        if mode == "record" and upstream is None:
            raise ValueError("Recording requires an explicit upstream transport")
        self.journal, self.upstream, self.budget = journal, upstream, budget
        self.mode, self.recover = mode, recover
        self.allowed_hosts = set(allowed_hosts or ())
        self._prefix = journal.records()
        self.position = 0
        self.fatal = None
        self.replayed_attempts = 0
        self.network_attempts = 0
        if mode == "record" and self._prefix and not recover:
            raise UncertainCapture("Existing capture requires explicit recovery; refusing duplicate API calls")

    def raise_if_failed(self):
        if self.fatal is not None:
            raise self.fatal

    def _fatal(self, error):
        self.fatal = error
        raise error

    def assert_consumed(self, operation_id=None):
        self.raise_if_failed()
        remaining = self._prefix[self.position:]
        if operation_id is not None:
            remaining = [row for row in remaining if row["context"].get("operation_id") == operation_id]
        if remaining:
            self._fatal(MissingCapture("Recorded HTTP attempts were not consumed: %s" % len(remaining)))
        return {"consumed": self.position, "recorded_prefix": len(self._prefix),
                "replayed_attempts": self.replayed_attempts, "network_attempts": self.network_attempts}

    def _reuse(self, record, request, request_record, context):
        if record["request_sha256"] != fingerprint(request_record) or record["request"] != request_record:
            self._fatal(MissingCapture("HTTP request mismatch at sequence %s (operation %s)" %
                                      (record["sequence"], context.get("operation_id"))))
        if record["context"] != context:
            self._fatal(MissingCapture("HTTP scope/order mismatch at sequence %s" % record["sequence"]))
        if record["status"] not in {"complete", "error"}:
            self._fatal(UncertainCapture("HTTP request %s has no complete known outcome (%s); no automatic resend" %
                                        (record["sequence"], record["status"])))
        self.position += 1
        self.replayed_attempts += 1
        if record["status"] == "error":
            if self.mode == "record" and self.budget and record.get("budget_id"):
                self.budget.settle(record["budget_id"])
            error = record.get("error") or {}
            kind = getattr(httpx, error.get("type", ""), None)
            if not isinstance(kind, type) or not issubclass(kind, httpx.RequestError):
                self._fatal(MissingCapture("Cannot faithfully replay recorded exception: " + str(error.get("type"))))
            raise kind(error.get("message", "Recorded HTTP error"), request=request)
        response = record.get("response") or {}
        if not response.get("complete") or response.get("redacted"):
            self._fatal(UncertainCapture("Recorded response is incomplete or redacted"))
        if not isinstance(response.get("body_base64"), str) or fingerprint(response["body_base64"]) != response.get("body_sha256"):
            self._fatal(MissingCapture("Recorded raw response fingerprint mismatch at sequence %s" % record["sequence"]))
        try:
            raw = _bytes(response["body_base64"])
        except (ValueError, TypeError):
            self._fatal(MissingCapture("Recorded response bytes are invalid"))
        if self.mode == "record" and self.budget and record.get("budget_id"):
            # Crash between response persistence and budget settlement is safe:
            # settle the original reservation rather than charge a second attempt.
            self.budget.settle(record["budget_id"], response.get("usage"))
        return httpx.Response(response["status_code"], headers=response["headers"],
                              stream=httpx.ByteStream(raw), request=request)

    async def handle_async_request(self, request):
        self.raise_if_failed()
        try:
            return await self._handle(request)
        except CaptureBoundaryError as exc:
            self.fatal = exc
            raise

    async def _handle(self, request):
        body = await request.aread()
        secrets = _secrets(request)
        protected = _protect_bytes(body, secrets)
        if protected != body:
            self._fatal(UncertainCapture("Request body contains an authorization secret; capture refused"))
        try:
            document = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            document = None
        # A supported model request carries credentials in excluded headers.
        # Refuse credential-bearing bodies rather than save a lossy substitute.
        if isinstance(document, dict) and clean(document, secrets) != document:
            self._fatal(UncertainCapture("Request body contains credential fields; capture refused"))
        context = clean(current_scope(), secrets)
        request_record = {"method": request.method, "url": _url(request.url),
                          "headers": _headers(request.headers, _REQUEST_HEADERS),
                          "body": document, "body_base64": _b64(body),
                          "sdk_retry_index": request.headers.get("x-stainless-retry-count")}
        if self.position < len(self._prefix):
            return self._reuse(self._prefix[self.position], request, request_record, context)
        if self.mode == "replay":
            self._fatal(MissingCapture("Missing recorded HTTP response at sequence %s, operation %s, purpose %s" %
                                      (self.position + 1, context.get("operation_id"), context.get("purpose"))))
        if self.allowed_hosts and request.url.host not in self.allowed_hosts:
            self._fatal(UncertainCapture("Model request host is not in the explicit allowlist"))
        if request.url.username or request.url.password or "[REDACTED]" in request_record["url"]:
            self._fatal(UncertainCapture("Credentials in URL are not supported by the capture transport"))
        reservation = self.budget.reserve(document, context) if self.budget else None
        sequence = self.journal.start(request_record, context, reservation)
        started = time.monotonic()
        response = None
        chunks = []
        network_token = network_allowed.set(True)
        network_dns_hosts[request.url.host] += 1
        try:
            self.network_attempts += 1
            response = await self.upstream.handle_async_request(request)
            headers = clean(_headers(response.headers, _RESPONSE_HEADERS), secrets)
            self.journal.event("http_response_headers", {"call_sequence": sequence,
                               "status_code": response.status_code, "headers": headers})
            if response.is_stream_consumed:
                chunks.append(response.content)
                # Preloaded responses have already been decompressed by httpx.
                headers = [[k, v] for k, v in headers if k.lower() not in {"content-encoding", "content-length"}]
                self.journal.event("http_response_chunk", {"call_sequence": sequence,
                                   "chunk": 0, "byte_count": len(response.content),
                                   "sha256": hashlib.sha256(response.content).hexdigest()})
            else:
                async for chunk in response.aiter_raw():
                    chunks.append(chunk)
                    self.journal.event("http_response_chunk", {"call_sequence": sequence,
                                       "chunk": len(chunks) - 1, "byte_count": len(chunk),
                                       "sha256": hashlib.sha256(chunk).hexdigest()})
        except Exception as exc:
            self.journal.fail(sequence, {"type": type(exc).__name__, "message": clean(str(exc), secrets),
                                        "elapsed_seconds": time.monotonic() - started,
                                        "partial_bytes": sum(map(len, chunks)), "response_started": response is not None})
            if self.budget:
                self.budget.settle(reservation)
            raise
        except BaseException as exc:
            # Pending is intentional: the provider may have completed a billed
            # request. It is unsafe to infer non-execution from a local interrupt.
            self.journal.event("http_interrupted", {"call_sequence": sequence, "type": type(exc).__name__,
                                                   "partial_bytes": sum(map(len, chunks))})
            self.fatal = UncertainCapture("HTTP request interrupted with unknown provider outcome")
            raise
        finally:
            network_allowed.reset(network_token)
            network_dns_hosts[request.url.host] -= 1
            if not network_dns_hosts[request.url.host]:
                del network_dns_hosts[request.url.host]
            if response is not None:
                await response.aclose()
        raw = b"".join(chunks)
        try:
            decoded = httpx.Response(200, headers=headers, content=raw).content
        except httpx.DecodingError:
            decoded = raw
        contains_secret = _protect_bytes(raw, secrets) != raw or _protect_bytes(decoded, secrets) != decoded
        try:
            # JSON escape sequences must not hide an echoed credential either.
            expanded = json.dumps(json.loads(decoded), ensure_ascii=False).encode("utf-8")
        except (ValueError, UnicodeDecodeError, TypeError):
            expanded = b""
        contains_secret = contains_secret or _protect_bytes(expanded, secrets) != expanded
        # Chunk metadata was durable, but bytes stayed in memory until this
        # whole-body check. A credential split across chunks or hidden by gzip
        # therefore never enters the journal. Do not save even a lossy response
        # body when a provider echoes an authorization secret.
        protected = b"" if contains_secret else raw
        streamed = bool(isinstance(document, dict) and document.get("stream"))
        unclean_metadata = _response_metadata(raw, headers, streamed)
        metadata = clean(unclean_metadata, secrets)
        contains_secret = contains_secret or metadata != unclean_metadata
        if contains_secret:
            protected = b""
        complete = (not streamed or response.status_code >= 400 or
                    (metadata["stream_done"] is True and bool(metadata["finish_reasons"])))
        recorded = {"status_code": response.status_code, "headers": headers,
                    "body_base64": _b64(protected), "body_sha256": fingerprint(_b64(protected)),
                    "chunk_count": len(chunks), "elapsed_seconds": time.monotonic() - started,
                    "complete": complete and not contains_secret, "redacted": contains_secret, **metadata}
        self.journal.finish(sequence, recorded, "complete" if complete and not contains_secret else "incomplete")
        if self.budget:
            self.budget.settle(reservation, metadata.get("usage"))
        if not complete or contains_secret:
            self._fatal(UncertainCapture("Response is incomplete or contained a secret; cannot be accepted for exact replay"))
        return httpx.Response(response.status_code, headers=headers, stream=httpx.ByteStream(raw), request=request)

    async def aclose(self):
        if self.upstream is not None:
            await self.upstream.aclose()
