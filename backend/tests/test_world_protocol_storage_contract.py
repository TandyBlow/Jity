"""Exercise the standalone stage-0 SQL contract, not production migrations."""

import json
from pathlib import Path
import sqlite3

import pytest

ARTIFACTS = Path(__file__).resolve().parents[2] / "design" / "world-protocol" / "v1"


def load(name):
    return json.loads((ARTIFACTS / "fixtures" / name).read_text(encoding="utf-8"))


def encoded(value):
    return None if value is None else json.dumps(value, ensure_ascii=False)


def insert_point(db, value, **extra):
    names = {"worldId": "world_id", "id": "id", "sequence": "sequence", "kind": "kind",
             "previousPointId": "previous_point_id", "roundId": "round_id", "advanceId": "advance_id",
             "trigger": "trigger", "linkedFromPointId": "linked_from_point_id",
             "timeAdvance": "time_advance", "entityDeltas": "entity_deltas"}
    row = {column: encoded(value[key]) if key in ("timeAdvance", "entityDeltas") else value[key]
           for key, column in names.items()}
    row.update(state_hash="stage0_fixture_hash", **extra)
    db.execute(f"INSERT INTO world_points ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))


def insert_checkpoint(db, value):
    adv = value["advance"]
    row = {"world_id": "world_school", "round_id": value["roundId"], "advance_id": adv["advanceId"],
           "input_id": adv["inputId"], "input_text": adv["inputText"], "intent_status": adv["intentStatus"],
           "revision": 1, "trigger": value["trigger"], "phase": value["phase"], "resume_phase": value["resumePhase"],
           "pending_group_json": encoded(value["pendingGroup"]), "conclusion_json": encoded(value["conclusion"]),
           "order_json": encoded(value["order"]), "cursor": value["cursor"],
           "acted_ids_json": encoded(value["actedIds"]), "visited_ids_json": encoded(value["visitedIds"])}
    db.execute(f"INSERT INTO world_round_checkpoints ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.executescript((ARTIFACTS / "storage-contract.sql").read_text(encoding="utf-8"))
    conn.execute("INSERT INTO worlds(id,initial_json) VALUES (?,?)", ("world_school", encoded(load("school.initial.json"))))
    yield conn
    conn.close()


def root(db, ready=True):
    insert_point(db, load("associated-points.json")["root"], narration_status="ready" if ready else "pending")
    db.execute("UPDATE worlds SET active_point_id='root_0' WHERE id='world_school'")


def test_root_and_first_point_coexist_with_nullable_round_columns(db):
    root(db)
    insert_checkpoint(db, load("associated-points.json")["checkpoints"][0])
    insert_point(db, load("associated-points.json")["points"][0])
    db.commit()
    assert db.execute("SELECT kind,round_id FROM world_points ORDER BY sequence").fetchall() == [
        ("root", None), ("normal", "round_1")]


def test_first_round_rejected_until_root_narration_is_ready(db):
    root(db, ready=False)
    checkpoint = load("associated-points.json")["checkpoints"][0]
    with pytest.raises(sqlite3.IntegrityError, match="head_narration_not_ready"):
        insert_checkpoint(db, checkpoint)
    db.execute("UPDATE world_points SET narration_status='ready' WHERE id='root_0'")
    insert_checkpoint(db, checkpoint)
    db.commit()


def test_second_root_is_rejected(db):
    root(db)
    value = load("associated-points.json")["root"]
    value["id"] = "second_root"
    with pytest.raises(sqlite3.IntegrityError):
        insert_point(db, value)


def test_second_successor_is_rejected(db):
    root(db)
    insert_checkpoint(db, load("associated-points.json")["checkpoints"][0])
    value = load("associated-points.json")["points"][0]
    insert_point(db, value)
    value.update(id="branch", sequence=2)
    with pytest.raises(sqlite3.IntegrityError):
        insert_point(db, value)


@pytest.mark.parametrize("field", ["previousPointId", "roundId", "advanceId", "trigger", "timeAdvance", "entityDeltas"])
def test_root_rejects_nonnull_progression_fields(db, field):
    value = load("associated-points.json")["root"]
    value[field] = {} if field in ("timeAdvance", "entityDeltas") else "invalid"
    with pytest.raises(sqlite3.IntegrityError):
        insert_point(db, value)


def test_root_head_claim_binds_epoch_without_an_advance_row(db):
    value = load("associated-points.json")["root"]
    insert_point(db, value, narration_generation=1, narration_claim_token="claim_root",
                 narration_claim_mode="head", narration_claim_fence_epoch=7, narration_claim_expires_at=180)
    db.commit()
    assert db.execute("SELECT advance_id,narration_claim_fence_epoch FROM world_points").fetchone() == (None, 7)


@pytest.mark.parametrize("mode,epoch", [("head", None), ("history", 7), (None, None), ("advance", 7)])
def test_claim_mode_and_epoch_check_cannot_pass_via_sql_null(db, mode, epoch):
    with pytest.raises(sqlite3.IntegrityError):
        insert_point(db, load("associated-points.json")["root"], narration_generation=1,
                     narration_claim_token="claim_root", narration_claim_mode=mode,
                     narration_claim_fence_epoch=epoch, narration_claim_expires_at=180)


def test_historical_root_claim_has_no_epoch(db):
    insert_point(db, load("associated-points.json")["root"], narration_generation=1,
                 narration_claim_token="claim_history", narration_claim_mode="history",
                 narration_claim_fence_epoch=None, narration_claim_expires_at=180)
    db.commit()


@pytest.mark.parametrize("conclusion", [
    {}, {"kind": "handback", "closedBy": "model"},
    {"kind": "handback", "closedBy": "cancel", "cancelReason": None},
    {"kind": "handback", "closedBy": "cancel", "cancelReason": " \n\t"},
    {"kind": "handback", "closedBy": "cancel", "cancelReason": "\u3000\u00a0\u2028"},
    {"kind": "handback", "closedBy": "model", "cancelReason": "not_null"},
    {"kind": "continue", "closedBy": "cancel", "cancelReason": "cancel", "candidateCharacterIds": ["person_c"], "nextRoundId": "round_2"},
])
def test_conclusion_source_and_cancel_reason_are_enforced_by_sql(db, conclusion):
    root(db)
    value = load("advance-chain.json")["cancel"]
    value["conclusion"] = conclusion
    with pytest.raises(sqlite3.IntegrityError):
        insert_checkpoint(db, value)


def test_cancel_and_model_handback_have_different_persisted_sources(db):
    root(db)
    rows = load("advance-chain.json")
    insert_checkpoint(db, rows["cancel"])
    insert_checkpoint(db, rows["handback"])
    assert db.execute("SELECT json_extract(conclusion_json,'$.closedBy') FROM world_round_checkpoints ORDER BY round_id").fetchall() == [
        ("cancel",), ("model",)]


def test_automatic_checkpoint_cannot_reset_input_consumption(db):
    root(db)
    value = load("advance-chain.json")["automatic"]
    value["advance"]["intentStatus"] = "pending"
    with pytest.raises(sqlite3.IntegrityError):
        insert_checkpoint(db, value)
