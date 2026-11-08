"""Purpose separation now; trusted account ownership seam for later login."""

import json
import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.dependencies import db
from app.dependencies.save_scope import SaveScope, get_save_scope
from app.main import app


@pytest.mark.asyncio
async def test_purpose_lists_are_disjoint_and_copy_load_keep_source():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = {}
        for purpose in ("user", "development", "test"):
            headers = {"X-Jity-Save-Purpose": purpose}
            response = await client.post("/sessions", headers=headers, json={"game_name": "same-name"})
            assert response.status_code == 200
            session = response.json()
            assert session["save_purpose"] == purpose
            assert session["account_id"] is None
            created[purpose] = session["session_id"]

        for purpose, sid in created.items():
            headers = {"X-Jity-Save-Purpose": purpose}
            slots = (await client.get("/campaigns/slots", headers=headers)).json()["slots"]
            assert slots and all(s["save_purpose"] == purpose for s in slots)
            assert sid in {s["campaign_id"] for s in slots}
            assert not ({s["campaign_id"] for s in slots} & (set(created.values()) - {sid}))
            other_purpose = "test" if purpose != "test" else "user"
            hidden = await client.get("/campaigns/slots", headers=headers, params={"session_id": created[other_purpose]})
            assert hidden.json()["slots"] == []

        # Copies inherit the source session, never the request's current list tab.
        sid = created["test"]
        response = await client.post("/campaigns/slots", headers={"X-Jity-Save-Purpose": "user"},
                                     json={"session_id": sid, "slot_name": "copy"})
        assert response.status_code == 200
        slots = (await client.get("/campaigns/slots", params={"session_id": sid},
                                  headers={"X-Jity-Save-Purpose": "test"})).json()["slots"]
        copied = next(s for s in slots if s["slot_name"] == "copy")
        loaded = await client.post(f"/campaigns/slots/{copied['id']}/load", headers={"X-Jity-Save-Purpose": "user"})
        assert loaded.status_code == 200
        assert loaded.json()["session"]["save_purpose"] == "test"
        default = (await client.post("/sessions", json={})).json()
        assert default["save_purpose"] == "development"
        for purpose in ("legacy", "invalid"):
            response = await client.post("/sessions", json={}, headers={"X-Jity-Save-Purpose": purpose})
            assert response.status_code == 422


@pytest.mark.asyncio
async def test_owner_is_server_derived_and_slot_operations_cannot_cross_accounts():
    # This override models a FUTURE authenticated principal; no account-header
    # mechanism or login is introduced by this feature.
    scope = SaveScope(account_id="account-a", purpose="user")
    app.dependency_overrides[get_save_scope] = lambda: scope
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            a = (await client.post("/sessions", json={"account_id": "account-b"})).json()
            assert a["account_id"] == "account-a"
            slots = (await client.get("/campaigns/slots")).json()["slots"]
            slot = next(s for s in slots if s["campaign_id"] == a["session_id"])
            scope = SaveScope(account_id="account-b", purpose="user")
            b = (await client.post("/sessions", json={})).json()
            own = (await client.get("/campaigns/slots")).json()["slots"]
            assert {s["campaign_id"] for s in own} == {b["session_id"]}
            assert (await client.get("/campaigns/slots", params={"session_id": a["session_id"]})).json()["slots"] == []
            assert (await client.post(f"/campaigns/slots/{slot['id']}/load")).status_code == 404
            assert (await client.delete(f"/campaigns/slots/{slot['id']}")).status_code == 404
            assert (await client.post("/campaigns/slots", json={"session_id": a["session_id"], "slot_name": "stolen"})).status_code == 404
            assert db.read_campaign_progress_by_id(slot["id"]) is not None

        # A client cannot opt into an account through a header or a query string.
        app.dependency_overrides.pop(get_save_scope)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            headers = {"X-Jity-Save-Purpose": "user", "X-Jity-Account-Id": "account-a"}
            listed = (await client.get("/campaigns/slots", headers=headers, params={"account_id": "account-a"})).json()["slots"]
            assert all(s["account_id"] is None for s in listed)
            assert (await client.delete(f"/campaigns/slots/{slot['id']}", headers=headers)).status_code == 404
    finally:
        app.dependency_overrides.pop(get_save_scope, None)


def test_old_database_migration_is_non_destructive_and_repeatable(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("""CREATE TABLE game_sessions (
            id TEXT PRIMARY KEY, game_name TEXT NOT NULL, model TEXT NOT NULL,
            state_json TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        connection.execute("INSERT INTO game_sessions(id, game_name, model, state_json) VALUES (?, ?, ?, ?)",
                           ("old", "test_named_but_unknown", "test-model", '{"turn":7}'))
    migrated = Database(path)
    row = migrated.get_session("old")
    assert row["account_id"] is None and row["save_purpose"] == "legacy"
    assert json.loads(row["state_json"]) == {"turn": 7}
    # Later state updates must not change ownership or classify an old save.
    migrated.write_session("old", row["game_name"], row["model"], {"turn": 8})
    row = Database(path).get_session("old")
    assert row["account_id"] is None and row["save_purpose"] == "legacy"
    assert json.loads(row["state_json"]) == {"turn": 8}


def test_pytest_database_is_not_the_user_database():
    from pathlib import Path
    assert db.path.resolve() != (Path(__file__).resolve().parents[1] / "data/jity.sqlite3").resolve()
    assert db.path.parent.name.startswith("jity-pytest-")
