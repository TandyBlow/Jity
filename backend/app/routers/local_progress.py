"""Standalone progress-sync router.

Mount this router without touching the existing world routes:

    from app.routers.local_progress import router
    app.include_router(router)

The router owns no game semantics. It stores an opaque LocalGameSnapshot and
answers head/read/upload-CAS/fork/select requests.
"""

from __future__ import annotations

import hmac
import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.schemas.local_progress import (
    GraphResponse,
    HeadResponse,
    SelectHeadRequest,
    SelectHeadResponse,
    SnapshotResponse,
    SnapshotUploadRequest,
    UploadResponse,
)
from app.services.local_progress import settings as progress_settings
from app.services.local_progress.store import LocalProgressStore, ProgressError

router = APIRouter(prefix="/local-progress", tags=["local-progress"])

_default_store: LocalProgressStore | None = None
_default_store_lock = threading.Lock()


def get_store(request: Request) -> LocalProgressStore:
    store = getattr(request.app.state, "local_progress_store", None)
    if store is not None:
        return store
    global _default_store
    with _default_store_lock:
        if _default_store is None:
            _default_store = progress_settings.build_store()
        return _default_store


def require_token(request: Request) -> None:
    if hasattr(request.app.state, "local_progress_token"):
        token = request.app.state.local_progress_token
    else:
        token = progress_settings.access_token()
    if not token:
        return
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(value.strip(), token):
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "missing or invalid bearer token"},
            headers={"WWW-Authenticate": "Bearer"},
        )


def _raise(exc: ProgressError) -> None:
    detail: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.head is not None:
        detail["head"] = exc.head
    if exc.branches:
        detail["branches"] = exc.branches
    raise HTTPException(status_code=exc.status, detail=detail) from exc


def _store_error(exc: ProgressError) -> None:
    _raise(exc)


@router.get("/health")
def health(store: LocalProgressStore = Depends(get_store)) -> dict[str, Any]:
    return store.health()


@router.get("/worlds/{world_id}/head", response_model=HeadResponse)
def head(
    world_id: str,
    store: LocalProgressStore = Depends(get_store),
    _: None = Depends(require_token),
) -> dict[str, Any]:
    try:
        return store.head(world_id)
    except ProgressError as exc:
        _store_error(exc)
    raise AssertionError("unreachable")


@router.get("/worlds/{world_id}/graph", response_model=GraphResponse)
def graph(
    world_id: str,
    store: LocalProgressStore = Depends(get_store),
    _: None = Depends(require_token),
) -> dict[str, Any]:
    try:
        return store.graph(world_id)
    except ProgressError as exc:
        _store_error(exc)
    raise AssertionError("unreachable")


@router.get("/worlds/{world_id}/snapshots/{snapshot_id}", response_model=SnapshotResponse)
def read_snapshot(
    world_id: str,
    snapshot_id: str,
    store: LocalProgressStore = Depends(get_store),
    _: None = Depends(require_token),
) -> dict[str, Any]:
    try:
        return store.read_snapshot(world_id, snapshot_id)
    except ProgressError as exc:
        _store_error(exc)
    raise AssertionError("unreachable")


@router.post("/worlds/{world_id}/snapshots", response_model=UploadResponse)
def upload(
    world_id: str,
    body: SnapshotUploadRequest,
    response: Response,
    store: LocalProgressStore = Depends(get_store),
    _: None = Depends(require_token),
) -> dict[str, Any]:
    try:
        result = store.upload(world_id, body)
    except ProgressError as exc:
        _store_error(exc)
    response.status_code = 201 if result["created"] and not result["idempotent"] else 200
    return result


@router.post("/worlds/{world_id}/head", response_model=SelectHeadResponse)
def select_head(
    world_id: str,
    body: SelectHeadRequest,
    store: LocalProgressStore = Depends(get_store),
    _: None = Depends(require_token),
) -> dict[str, Any]:
    try:
        return store.select_head(world_id, body)
    except ProgressError as exc:
        _store_error(exc)
    raise AssertionError("unreachable")
