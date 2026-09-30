"""Integration tests: campaign load → opening_scene → inject_context → anchor evaluation via API."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_create_session_with_campaign():
    """POST /sessions with campaign_filename loads campaign and returns opening_scene."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/sessions", json={
            "game_name": "wiring_test",
            "model": "deepseek-v4-flash",
            "campaign_filename": "default_campaign.json",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]
        # opening_scene should come from campaign, not ScriptedStory default
        assert "卡塞尔学院" in str(data["state"]["current_location"])


@pytest.mark.asyncio
async def test_create_session_campaign_not_found():
    """POST /sessions with nonexistent campaign returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/sessions", json={
            "game_name": "test",
            "campaign_filename": "nonexistent.json",
        })
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in str(data.get("detail", "")).lower()


@pytest.mark.asyncio
async def test_create_session_defaults_to_campaign():
    """Omitting the filename selects the default campaign, never free play."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/sessions", json={
            "game_name": "normal_test",
            "model": None,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]
        assert data["campaign_filename"] == "default_campaign.json"
        assert data["state"]["current_location"]


@pytest.mark.asyncio
async def test_list_slots_filters_by_session_id():
    """GET /campaigns/slots?session_id=... should not return other sessions' default slots."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/sessions", json={
            "game_name": "slot_filter_1",
            "model": "deepseek-v4-flash",
            "campaign_filename": "default_campaign.json",
        })
        second = await client.post("/sessions", json={
            "game_name": "slot_filter_2",
            "model": "deepseek-v4-flash",
            "campaign_filename": "default_campaign.json",
        })
        assert first.status_code == 200
        assert second.status_code == 200

        first_id = first.json()["session_id"]
        second_id = second.json()["session_id"]
        resp = await client.get("/campaigns/slots", params={"session_id": first_id})

        assert resp.status_code == 200
        slots = resp.json()["slots"]
        assert slots
        assert {slot["campaign_id"] for slot in slots} == {first_id}
        assert second_id not in {slot["campaign_id"] for slot in slots}


@pytest.mark.asyncio
async def test_delete_slot_by_id_removes_non_active_slot():
    """DELETE /campaigns/slots/{id} removes a non-active slot of the session."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/sessions", json={
            "game_name": "slot_delete_test",
            "model": "deepseek-v4-flash",
            "campaign_filename": "default_campaign.json",
        })
        session_id = created.json()["session_id"]
        # 新建命名槽会立即成为 active，原来的 auto 槽因此可删除
        await client.post("/campaigns/slots", json={"slot_name": "keep", "session_id": session_id})

        slots = (await client.get("/campaigns/slots", params={"session_id": session_id})).json()["slots"]
        target = next(slot for slot in slots if not slot["is_active"])
        resp = await client.delete(f"/campaigns/slots/{target['id']}")

        assert resp.status_code == 200
        assert resp.json()["slot_name"] == target["slot_name"]
        remaining = (await client.get("/campaigns/slots", params={"session_id": session_id})).json()["slots"]
        assert target["id"] not in {slot["id"] for slot in remaining}
        assert any(slot["slot_name"] == "keep" for slot in remaining)


@pytest.mark.asyncio
async def test_delete_active_slot_rejected():
    """Deleting the session's active slot returns 409 and keeps the row."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/sessions", json={
            "game_name": "slot_delete_active_test",
            "model": "deepseek-v4-flash",
            "campaign_filename": "default_campaign.json",
        })
        session_id = created.json()["session_id"]

        slots = (await client.get("/campaigns/slots", params={"session_id": session_id})).json()["slots"]
        active = next(slot for slot in slots if slot["is_active"])
        resp = await client.delete(f"/campaigns/slots/{active['id']}")

        assert resp.status_code == 409
        remaining = (await client.get("/campaigns/slots", params={"session_id": session_id})).json()["slots"]
        assert active["id"] in {slot["id"] for slot in remaining}


@pytest.mark.asyncio
async def test_delete_slot_not_found():
    """Deleting an unknown slot id returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/campaigns/slots/987654321")
        assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_slot_is_scoped_to_one_session():
    """同名槽分属不同会话时，按 id 删除只影响目标会话（旧的按名删除会全部误删）。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session_ids = []
        for name in ("slot_delete_scope_a", "slot_delete_scope_b"):
            created = await client.post("/sessions", json={
                "game_name": name,
                "model": "deepseek-v4-flash",
                "campaign_filename": "default_campaign.json",
            })
            session_id = created.json()["session_id"]
            session_ids.append(session_id)
            await client.post("/campaigns/slots", json={"slot_name": "dup", "session_id": session_id})
            await client.post("/campaigns/slots", json={"slot_name": "later", "session_id": session_id})

        slots_a = (await client.get("/campaigns/slots", params={"session_id": session_ids[0]})).json()["slots"]
        dup_a = next(slot for slot in slots_a if slot["slot_name"] == "dup")
        resp = await client.delete(f"/campaigns/slots/{dup_a['id']}")
        assert resp.status_code == 200

        slots_b = (await client.get("/campaigns/slots", params={"session_id": session_ids[1]})).json()["slots"]
        assert any(slot["slot_name"] == "dup" for slot in slots_b)
