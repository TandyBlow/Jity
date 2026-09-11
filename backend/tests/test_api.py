"""API endpoint smoke tests using httpx AsyncClient with ASGITransport."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_create_session():
    """POST /sessions creates a new game session."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/sessions", json={
            "game_name": "测试角色",
            "model": None,
        })
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["game_name"] == "测试角色"


@pytest.mark.asyncio
async def test_get_session_not_found():
    """GET /sessions/{id} returns 404 for nonexistent session."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sessions/nonexistent-id")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_knowledge_reload():
    """POST /knowledge/reload returns success."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/knowledge/reload")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_save_campaign_rejects_path_traversal():
    """POST /campaigns/save must not write outside campaigns_dir."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/campaigns/save", json={
            "filename": "../traversal_probe",
            "campaign": {"version": 3, "title": "x"},
        })
    assert response.status_code == 400
    from app.config import get_settings

    probe = get_settings().campaigns_dir.parent / "traversal_probe.json"
    assert not probe.exists()


@pytest.mark.asyncio
async def test_get_campaign_file_rejects_path_traversal():
    """GET /campaigns/{filename} must not escape campaigns_dir."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/campaigns/..%2Ftraversal_probe.json")
    assert response.status_code in (400, 404)
