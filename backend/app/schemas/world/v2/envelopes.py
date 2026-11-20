"""v2 response envelopes: OperationResult, ContextResponse, ErrorResponse.

`data` carries result identity, status and binding digests only — never
inputText. The input text is readable solely through GET context's
`activeInput`, so replaying or re-reading old responses cannot revive cleaned
input. Claim tokens appear only in narration-jobs/claim data; lease tokens only
in lease-granting operation data.
"""

from typing import Any, Generic, TypeVar, Literal

from pydantic import ConfigDict, Field, model_validator

from app.schemas.world.contracts import Contract, Id, Text

from .base import Envelope
from .contexts import ControlState, PointWorkView, WorldContext, RecoveryView
from .errors import ClientAction, ErrorCode, ERROR_CODES
from .registry import OperationName

T = TypeVar("T")


class OperationResult(Envelope, Generic[T]):
    """Uniform success envelope for every registry operation with a body."""

    replayed: bool
    operation: OperationName
    requestId: Id
    requestHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    world: WorldContext
    control: ControlState
    work: PointWorkView | None
    data: T


class ActiveInput(Contract):
    """The unfinished input chain's text; GET context is its only carrier."""

    advanceId: Id
    inputId: Id
    text: Text


class ContextResponse(Envelope):
    """GET /worlds/{worldId}/context response; no requestId, no tokens."""

    world: WorldContext
    control: ControlState
    work: PointWorkView | None
    activeInput: ActiveInput | None
    recovery: RecoveryView | None

    @model_validator(mode="after")
    def recovery_scope(self):
        if self.recovery is None:
            return self
        if self.world.lease is None or self.recovery.fenceEpoch != self.world.lease.fenceEpoch:
            raise ValueError("recovery does not belong to the current epoch")
        current = self.recovery.current
        if current is not None and current.work != self.work:
            raise ValueError("recovery differs from the current work snapshot")
        successor = self.recovery.successor
        if successor is not None:
            if self.world.successor is None or successor.work.pointId != self.world.successor.pointId:
                raise ValueError("recovery does not belong to the reserved successor")
            if successor.work.baseline != self.world.successor.baseline:
                raise ValueError("successor baseline differs from its reservation")
        return self


class ReadResult(Envelope, Generic[T]):
    """Envelope for the remaining read operations (list_points, get_state,
    narration_get); like ContextResponse it carries no requestId."""

    world: WorldContext
    data: T


class ComputeResult(Envelope, Generic[T]):
    """Stateless preview: no request key, replay flag or idempotency digest."""

    operation: Literal["preview_point"]
    world: WorldContext
    control: ControlState
    work: PointWorkView | None
    data: T


class ErrorBody(Contract):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        *[{"if": {"properties": {"code": {"const": code}}},
           "then": {"properties": {
               key: {"const": spec[key]} for key in ("httpStatus", "retryable", "clientAction")}}}
          for code, spec in ERROR_CODES.items()],
        {"if": {"properties": {"code": {"const": "preview_budget_exceeded"}}},
         "then": {"properties": {"details": {"required": ["limit"],
                                             "properties": {"limit": {"enum": ["request", "response"]}}}}}},
    ]})

    code: ErrorCode
    httpStatus: int = Field(ge=400, le=499)
    retryable: bool
    clientAction: ClientAction
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def matches_error_table(self):
        spec = ERROR_CODES[self.code]
        if self.httpStatus != spec["httpStatus"] or self.retryable != spec["retryable"]:
            raise ValueError(f"status/retryable for {self.code} must match the error table")
        if self.clientAction != spec["clientAction"]:
            raise ValueError(f"clientAction for {self.code} must match the error table")
        if self.code == "preview_budget_exceeded":
            if self.details.get("limit") not in ("request", "response"):
                raise ValueError("preview_budget_exceeded needs details.limit=request|response")
        return self


class ErrorResponse(Envelope):
    """Uniform error envelope; world/control/work snapshots are optional and
    required by controlRequired codes."""

    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"allOf": [
        {"if": {"properties": {"error": {"properties": {"code": {"enum": sorted(
            code for code, spec in ERROR_CODES.items() if spec["controlRequired"])}}}}},
         "then": {"required": ["control"], "properties": {"control": {"type": "object"}}}},
        {"if": {"properties": {"error": {"properties": {"code": {"enum": [
            "request_id_reused", "request_in_progress"]}}}}},
         "then": {"required": ["operation", "requestId"], "properties": {
             "operation": {"type": "string"}, "requestId": {"type": "string"}}}},
    ]})

    replayed: bool
    operation: OperationName | None
    requestId: Id | None
    worldId: Id | None
    error: ErrorBody
    world: WorldContext | None = None
    control: ControlState | None = None
    work: PointWorkView | None = None

    @model_validator(mode="after")
    def control_where_required(self):
        if self.error.code in ("request_id_reused", "request_in_progress"):
            if self.operation is None or self.requestId is None:
                raise ValueError("request-keyed errors must name operation and requestId")
        if ERROR_CODES[self.error.code]["controlRequired"] and self.control is None:
            raise ValueError(f"{self.error.code} errors must carry a control snapshot")
        return self
