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
