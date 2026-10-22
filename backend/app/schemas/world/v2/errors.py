"""v2 runtime error-code table.

`contract_mismatch` is deliberately absent: it belongs to CI/pin checking only.
A wire-version mismatch at runtime is `protocol_version_unsupported`; a payload
or engine mismatch is `version_mismatch`. The per-code HTTP status, retryable
flag, clientAction and controlRequired here are the single authority that both
the ErrorResponse validator and the exported api-contract.json must match.
"""

from typing import Literal

ErrorCode = Literal[
    "narration_blocked",
    "cache_missing",
    "claim_expired",
    "claim_fenced",
    "paused",
    "stale_epoch",
    "lease_invalid",
    "revision_mismatch",
    "phase_invalid",
    "version_mismatch",
    "protocol_version_unsupported",
    "request_id_reused",
    "request_in_progress",
    "point_time_locked",
    "frozen_work_missing",
    "frozen_work_corrupt",
    "preview_budget_exceeded",
    "request_malformed",
]

ClientAction = Literal[
    "retry_same_request",
    "reacquire_lease",
    "refresh_context",
    "wait_narration",
    "regenerate_narration",
    "resolve_gate",
    "pause",
    "fix_request",
    "none",
]

# Codes whose ErrorResponse must carry a control snapshot so the client can
# resync without an extra context round-trip (plan IF-02: the 400-malformed
# class may omit it).
CONTROL_REQUIRED_CODES = frozenset({
    "narration_blocked", "paused", "stale_epoch", "revision_mismatch", "phase_invalid",
})

ERROR_CODES: dict[str, dict] = {
    # Compute or advance attempted while the head narration gate is unresolved.
    "narration_blocked": {"httpStatus": 409, "retryable": True, "clientAction": "wait_narration"},
    # Narration cache absent; regeneration must produce a new ready generation.
    "cache_missing": {"httpStatus": 409, "retryable": False, "clientAction": "regenerate_narration"},
    # Claim TTL lapsed; a fresh generation must be issued before narration work.
    "claim_expired": {"httpStatus": 409, "retryable": False, "clientAction": "regenerate_narration"},
    # Claim superseded by a newer generation or issued epoch.
    "claim_fenced": {"httpStatus": 409, "retryable": False, "clientAction": "refresh_context"},
    # Compute or advance attempted while paused=true.
    "paused": {"httpStatus": 409, "retryable": False, "clientAction": "resolve_gate"},
    # Writer lost the lease epoch to a takeover or a renewal race.
    "stale_epoch": {"httpStatus": 409, "retryable": False, "clientAction": "reacquire_lease"},
    # Missing, unknown, expired or still-held lease token for the requested grant.
    "lease_invalid": {"httpStatus": 409, "retryable": False, "clientAction": "reacquire_lease"},
    # expectedCheckpointRevision no longer matches the controller.
    "revision_mismatch": {"httpStatus": 409, "retryable": False, "clientAction": "refresh_context"},
    # Operation not allowed from the current phase or work position.
    "phase_invalid": {"httpStatus": 409, "retryable": False, "clientAction": "refresh_context"},
    # Head/point version, engine or payload identity mismatch; unknown identities.
    "version_mismatch": {"httpStatus": 409, "retryable": False, "clientAction": "refresh_context"},
    # Client wire dialect unknown or too new for this server.
    "protocol_version_unsupported": {"httpStatus": 400, "retryable": False, "clientAction": "none"},
    # Same requestId with a different operation or normalized request.
    "request_id_reused": {"httpStatus": 409, "retryable": False, "clientAction": "fix_request"},
    # First transaction for this requestId has not committed yet.
    "request_in_progress": {"httpStatus": 409, "retryable": True, "clientAction": "retry_same_request"},
    # Point time is locked by confirmed work; changing it needs an explicit cancel.
    "point_time_locked": {"httpStatus": 409, "retryable": False, "clientAction": "fix_request"},
    # Manifest-referenced frozen work row is absent; work stays for repair or cancel.
    "frozen_work_missing": {"httpStatus": 409, "retryable": False, "clientAction": "pause"},
    # Manifest-referenced frozen work row fails its content-hash binding.
    "frozen_work_corrupt": {"httpStatus": 409, "retryable": False, "clientAction": "pause"},
    # Preview request or response exceeded its byte budget.
    "preview_budget_exceeded": {"httpStatus": 413, "retryable": False, "clientAction": "fix_request"},
    # Schema-level malformed payload; may omit control and world snapshots.
    "request_malformed": {"httpStatus": 400, "retryable": False, "clientAction": "fix_request"},
}

for code, spec in ERROR_CODES.items():
    spec["controlRequired"] = code in CONTROL_REQUIRED_CODES
