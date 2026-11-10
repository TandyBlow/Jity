"""Focused tests for the standalone progress-sync store and router.

These tests only cover this lane's contract: lineage, content identity, CAS,
idempotent replay, branch preservation and device recovery. They do not load
the world engine or run model inference.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.local_progress import router
from app.services.local_progress.store import LocalProgressStore


def payload(turn: int, text: str = "玩家在门厅等待。", **extra: object) -> dict:
    """An opaque LocalGameSnapshot-shaped payload. The server must not parse it."""
    return {
        "transport": {
            "worldId": "w1",
            "round": turn,
            "state": {"characters": {"person_a": {"position": "hall"}}},
        },
        "commands": [text],
        **extra,
    }


def make_app(path, **store_kwargs) -> FastAPI:
    application = FastAPI()
    application.state.local_progress_store = LocalProgressStore(path, **store_kwargs)
    application.state.local_progress_token = None
    application.include_router(router)
    return application


@pytest.fixture
def client(tmp_path):
    with TestClient(make_app(tmp_path / "progress.sqlite3")) as test_client:
        yield test_client


def upload(
    client: TestClient,
    *,
    request_id: str,
    value: dict,
    expected_head: str | None,
    expected_revision: int,
    parents: list[str] | None = None,
    activate: bool = True,
    world: str = "w1",
):
    return client.post(
        f"/local-progress/worlds/{world}/snapshots",
        json={
            "requestId": request_id,
            "parentSnapshotIds": parents or [],
            "expectedHead": expected_head,
            "expectedRevision": expected_revision,
            "activate": activate,
            "payload": value,
        },
    )


def start(client: TestClient, value: dict | None = None, request_id: str = "root"):
    response = upload(
        client,
        request_id=request_id,
        value=value or payload(0),
        expected_head=None,
        expected_revision=0,
    )
    assert response.status_code == 201, response.text
    return response.json()


def advance(client: TestClient, root: dict, value: dict, request_id: str = "a2"):
    response = upload(
        client,
        request_id=request_id,
        value=value,
        expected_head=root["snapshotId"],
        expected_revision=root["revision"],
        parents=[root["snapshotId"]],
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_root_upload_head_and_opaque_readback(client):
    snapshot = payload(0, "开始。", arbitrary={"not": ["world", "semantics"]})
    created = start(client, snapshot)

    assert created["snapshotId"].startswith("snap_")
    assert len(created["contentDigest"]) == 64
    assert created["created"] is True
    assert created["changed"] is True
    assert created["revision"] == 1
    assert created["headSnapshotId"] == created["snapshotId"]
    assert created["parentSnapshotIds"] == []

    head = client.get("/local-progress/worlds/w1/head")
    assert head.status_code == 200
    assert head.json()["headSnapshotId"] == created["snapshotId"]
    assert head.json()["revision"] == 1

    read = client.get(f"/local-progress/worlds/w1/snapshots/{created['snapshotId']}")
    assert read.status_code == 200
    body = read.json()
    assert body["payload"] == snapshot
    assert body["parentSnapshotIds"] == []
    assert body["contentDigest"] == created["contentDigest"]


def test_content_identity_is_payload_hash_not_timestamp_or_request(client):
    first = payload(1, "同一份内容。")
    created = start(client, first)
    digest = hashlib.sha256(
        __import__("json").dumps(
            first, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    assert created["contentDigest"] == digest
    assert created["snapshotId"] == f"snap_{digest}"

    duplicate = upload(
        client,
        request_id="same-content",
        value=first,
        expected_head=created["snapshotId"],
        expected_revision=1,
        parents=[created["snapshotId"]],
    )
    assert duplicate.status_code == 200, duplicate.text
    body = duplicate.json()
    assert body["snapshotId"] == created["snapshotId"]
    assert body["created"] is False
    assert body["changed"] is False
    assert body["revision"] == 1

    graph = client.get("/local-progress/worlds/w1/graph").json()
    assert len(graph["nodes"]) == 1


def test_stale_revision_and_stale_head_are_rejected_without_moving_head(client):
    root = start(client)
    second = advance(client, root, payload(2))

    stale_revision = upload(
        client,
        request_id="stale-revision",
        value=payload(3),
        expected_head=root["snapshotId"],
        expected_revision=root["revision"],
        parents=[root["snapshotId"]],
    )
    assert stale_revision.status_code == 409
    detail = stale_revision.json()["detail"]
    assert detail["code"] == "revision_mismatch"
    assert detail["head"]["headSnapshotId"] == second["snapshotId"]
    assert detail["head"]["revision"] == 2

    wrong_head = upload(
        client,
        request_id="wrong-head",
        value=payload(3),
        expected_head=None,
        expected_revision=2,
        parents=[second["snapshotId"]],
    )
    assert wrong_head.status_code == 409
    assert wrong_head.json()["detail"]["code"] == "head_mismatch"

    head = client.get("/local-progress/worlds/w1/head").json()
    assert head["headSnapshotId"] == second["snapshotId"]
    assert head["revision"] == 2


def test_idempotent_replay_after_a_later_device_advances(client):
    first = payload(1, "设备A保存。")
    root = start(client, first, request_id="device-a-first")
    second = advance(client, root, payload(2, "设备A继续。"), request_id="device-a-second")

    replay = upload(
        client,
        request_id="device-a-first",
        value=first,
        expected_head=None,
        expected_revision=0,
    )
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["idempotent"] is True
    assert body["snapshotId"] == root["snapshotId"]
    assert body["headSnapshotId"] == second["snapshotId"]
    assert body["revision"] == 2
    assert body["changed"] is False

    reused = upload(
        client,
        request_id="device-a-first",
        value=payload(99),
        expected_head=None,
        expected_revision=0,
    )
    assert reused.status_code == 409
    assert reused.json()["detail"]["code"] == "request_id_reused"


def test_ancestor_cannot_overwrite_or_become_active_branch(client):
    root = start(client)
    second = advance(client, root, payload(2))

    overwrite = upload(
        client,
        request_id="ancestor-write",
        value=payload(9),
        expected_head=root["snapshotId"],
        expected_revision=root["revision"],
        parents=[root["snapshotId"]],
    )
    assert overwrite.status_code == 409
    assert overwrite.json()["detail"]["code"] == "revision_mismatch"

    select_ancestor = client.post(
        "/local-progress/worlds/w1/head",
        json={
            "requestId": "select-ancestor",
            "snapshotId": root["snapshotId"],
            "expectedHead": second["snapshotId"],
            "expectedRevision": 2,
        },
    )
    assert select_ancestor.status_code == 409
    assert select_ancestor.json()["detail"]["code"] == "not_branch_leaf"
    assert set(select_ancestor.json()["detail"]["branches"]) == {second["snapshotId"]}

    head = client.get("/local-progress/worlds/w1/head").json()
    assert head["headSnapshotId"] == second["snapshotId"]


def test_offline_fork_preserves_both_branches_and_choice_changes_only_active_head(client):
    root = start(client)
    branch_a = advance(client, root, payload(2, "A线。"), request_id="branch-a")

    branch_b_payload = payload(2, "B线从旧点继续。")
    fork = upload(
        client,
        request_id="branch-b-fork",
        value=branch_b_payload,
        expected_head=branch_a["snapshotId"],
        expected_revision=branch_a["revision"],
        parents=[root["snapshotId"]],
        activate=False,
    )
    assert fork.status_code == 201, fork.text
    branch_b = fork.json()
    assert branch_b["headSnapshotId"] == branch_a["snapshotId"]
    assert branch_b["revision"] == 3
    assert branch_b["parentSnapshotIds"] == [root["snapshotId"]]

    graph = client.get("/local-progress/worlds/w1/graph").json()
    assert set(graph["branches"]) == {branch_a["snapshotId"], branch_b["snapshotId"]}
    assert len(graph["nodes"]) == 3

    chosen = client.post(
        "/local-progress/worlds/w1/head",
        json={
            "requestId": "choose-b",
            "snapshotId": branch_b["snapshotId"],
            "expectedHead": branch_a["snapshotId"],
            "expectedRevision": 3,
        },
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["changed"] is True
    assert chosen.json()["revision"] == 4
    assert chosen.json()["headSnapshotId"] == branch_b["snapshotId"]

    head = client.get("/local-progress/worlds/w1/head").json()
    assert head["headSnapshotId"] == branch_b["snapshotId"]
    assert head["revision"] == 4

    a_read = client.get(f"/local-progress/worlds/w1/snapshots/{branch_a['snapshotId']}").json()
    b_read = client.get(f"/local-progress/worlds/w1/snapshots/{branch_b['snapshotId']}").json()
    assert a_read["payload"] == payload(2, "A线。")
    assert b_read["payload"] == branch_b_payload

    graph = client.get("/local-progress/worlds/w1/graph").json()
    assert set(graph["branches"]) == {branch_a["snapshotId"], branch_b["snapshotId"]}


def test_two_devices_can_restore_each_others_progress(client):
    device_a_first = start(client, payload(1, "A第一次。"), request_id="a-1")
    device_a_second = advance(
        client, device_a_first, payload(2, "A第二次。"), request_id="a-2"
    )

    # Device B starts with no local state: head + payload is enough to restore.
    b_head = client.get("/local-progress/worlds/w1/head").json()
    assert b_head["headSnapshotId"] == device_a_second["snapshotId"]
    b_restore = client.get(
        f"/local-progress/worlds/w1/snapshots/{b_head['headSnapshotId']}"
    ).json()
    assert b_restore["payload"] == payload(2, "A第二次。")

    b_upload = upload(
        client,
        request_id="b-1",
        value=payload(3, "B继续。"),
        expected_head=b_head["headSnapshotId"],
        expected_revision=b_head["revision"],
        parents=[b_head["headSnapshotId"]],
    )
    assert b_upload.status_code == 201, b_upload.text
    b_snapshot = b_upload.json()

    # Device A comes back and recovers B's progress.
    a_head = client.get("/local-progress/worlds/w1/head").json()
    assert a_head["headSnapshotId"] == b_snapshot["snapshotId"]
    a_restore = client.get(
        f"/local-progress/worlds/w1/snapshots/{a_head['headSnapshotId']}"
    ).json()
    assert a_restore["payload"] == payload(3, "B继续。")
    assert a_restore["parentSnapshotIds"] == [device_a_second["snapshotId"]]


def test_parent_and_lineage_validation(client):
    root = start(client)
    second = advance(client, root, payload(2))

    unknown_parent = upload(
        client,
        request_id="unknown-parent",
        value=payload(3),
        expected_head=second["snapshotId"],
        expected_revision=2,
        parents=[second["snapshotId"], "snap_" + "0" * 64],
    )
    assert unknown_parent.status_code == 400
    assert unknown_parent.json()["detail"]["code"] == "parent_unknown"

    missing_head_parent = upload(
        client,
        request_id="missing-head-parent",
        value=payload(3),
        expected_head=second["snapshotId"],
        expected_revision=2,
        parents=[],
    )
    assert missing_head_parent.status_code == 400
    assert missing_head_parent.json()["detail"]["code"] == "request_malformed"

    first_must_activate = upload(
        client,
        request_id="first-fork",
        value=payload(0, "另一个世界。"),
        expected_head=None,
        expected_revision=0,
        activate=False,
        world="w2",
    )
    assert first_must_activate.status_code == 400


def test_content_identity_cannot_create_a_lineage_cycle(client):
    root = start(client)
    second = advance(client, root, payload(2))

    # Re-uploading the root's identical payload while naming its descendant as
    # a parent would make root its own ancestor.
    cycle = upload(
        client,
        request_id="cycle",
        value=payload(0),
        expected_head=second["snapshotId"],
        expected_revision=2,
        parents=[second["snapshotId"]],
        activate=False,
    )
    assert cycle.status_code == 400
    assert cycle.json()["detail"]["code"] == "lineage_cycle"
    assert client.get("/local-progress/worlds/w1/head").json()["revision"] == 2


def test_select_replay_is_idempotent_and_does_not_move_head_twice(client):
    root = start(client)
    branch_a = advance(client, root, payload(2, "A"), request_id="a")
    fork = upload(
        client,
        request_id="b",
        value=payload(2, "B"),
        expected_head=branch_a["snapshotId"],
        expected_revision=2,
        parents=[root["snapshotId"]],
        activate=False,
    ).json()

    chosen = client.post(
        "/local-progress/worlds/w1/head",
        json={
            "requestId": "choose",
            "snapshotId": fork["snapshotId"],
            "expectedHead": branch_a["snapshotId"],
            "expectedRevision": 3,
        },
    )
    assert chosen.status_code == 200
    assert chosen.json()["revision"] == 4

    replay = client.post(
        "/local-progress/worlds/w1/head",
        json={
            "requestId": "choose",
            "snapshotId": fork["snapshotId"],
            "expectedHead": branch_a["snapshotId"],
            "expectedRevision": 3,
        },
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent"] is True
    assert replay.json()["revision"] == 4
    assert replay.json()["headSnapshotId"] == fork["snapshotId"]


def test_unknown_world_and_snapshot_return_404(client):
    assert client.get("/local-progress/worlds/missing/head").status_code == 404
    assert client.get("/local-progress/worlds/missing/graph").status_code == 404
    assert (
        client.get("/local-progress/worlds/missing/snapshots/snap_" + "0" * 64).status_code
        == 404
    )


def test_payload_limit_and_token_permission(tmp_path):
    limited = make_app(tmp_path / "limited.sqlite3", max_payload_bytes=64)
    with TestClient(limited) as client:
        response = upload(
            client,
            request_id="too-big",
            value=payload(0, "x" * 200),
            expected_head=None,
            expected_revision=0,
        )
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "payload_too_large"

    protected = make_app(tmp_path / "protected.sqlite3")
    protected.state.local_progress_token = "secret-token"
    with TestClient(protected) as client:
        denied = client.get("/local-progress/worlds/w1/head")
        assert denied.status_code == 401
        allowed = client.get(
            "/local-progress/worlds/w1/head",
            headers={"Authorization": "Bearer secret-token"},
        )
        assert allowed.status_code == 404


def test_malformed_payload_is_rejected_without_touching_storage(client):
    response = client.post(
        "/local-progress/worlds/w1/snapshots",
        content=(
            '{"requestId":"nan","parentSnapshotIds":[],"expectedHead":null,'
            '"expectedRevision":0,"activate":true,"payload":{"value":NaN}}'
        ),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "request_malformed"
    assert client.get("/local-progress/worlds/w1/head").status_code == 404
