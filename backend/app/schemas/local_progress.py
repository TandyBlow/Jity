"""Wire schemas for the progress-sync service.

The payload is deliberately typed as arbitrary JSON: it is the browser's
existing LocalGameSnapshot. This module never imports world-engine types and
never inspects the payload's game semantics.
"""

from typing import Any

from pydantic import BaseModel, Field


class SnapshotUploadRequest(BaseModel):
    requestId: str = Field(min_length=1, max_length=200)
    parentSnapshotIds: list[str] = Field(default_factory=list)
    expectedHead: str | None = None
    expectedRevision: int = Field(ge=0)
    activate: bool = True
    payload: Any


class SelectHeadRequest(BaseModel):
    requestId: str = Field(min_length=1, max_length=200)
    snapshotId: str
    expectedHead: str | None = None
    expectedRevision: int = Field(ge=0)


class HeadResponse(BaseModel):
    worldId: str
    headSnapshotId: str | None
    revision: int
    updatedAt: str | None = None


class SnapshotSummary(BaseModel):
    snapshotId: str
    parentSnapshotIds: list[str]
    contentDigest: str
    sizeBytes: int
    createdAt: str


class SnapshotResponse(SnapshotSummary):
    payload: Any


class UploadResponse(BaseModel):
    worldId: str
    snapshotId: str
    contentDigest: str
    parentSnapshotIds: list[str]
    headSnapshotId: str | None
    revision: int
    created: bool
    changed: bool
    idempotent: bool


class SelectHeadResponse(BaseModel):
    worldId: str
    headSnapshotId: str | None
    previousHeadSnapshotId: str | None
    revision: int
    changed: bool
    idempotent: bool


class GraphResponse(BaseModel):
    worldId: str
    headSnapshotId: str | None
    revision: int
    updatedAt: str | None = None
    nodes: list[SnapshotSummary]
    branches: list[str]
