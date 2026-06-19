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
async def test_create_session_without_campaign():
    """POST /sessions without campaign_filename works normally (backward compat)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/sessions", json={
            "game_name": "normal_test",
            "model": None,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"]
        # Without campaign, uses default state (ScriptedStory fallback)
        assert data["state"]["current_location"]
