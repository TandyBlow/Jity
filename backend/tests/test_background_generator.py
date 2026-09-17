"""Tests for cached AI scene backgrounds."""

import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.services.background_generator import BackgroundGenerationError, BackgroundGenerator


@pytest.mark.asyncio
async def test_background_generation_requires_api_key(tmp_path):
    generator = BackgroundGenerator(Settings(image_api_key="", backgrounds_dir=tmp_path))

    with pytest.raises(BackgroundGenerationError, match="IMAGE_API_KEY"):
        await generator.generate("gothic academy hall")


@pytest.mark.asyncio
async def test_background_generation_reuses_cached_image(tmp_path):
    settings = Settings(image_api_key="test-key", backgrounds_dir=tmp_path)
    generator = BackgroundGenerator(settings)
    generator.prompt_recorder.record = AsyncMock()
    prompt = generator._build_prompt("gothic academy hall", "卡塞尔学院")
    cache_key = hashlib.sha256(
        f"{settings.image_model}\0{settings.image_size}\0{prompt}".encode()
    ).hexdigest()
    cached_file = tmp_path / f"{cache_key}.png"
    cached_file.write_bytes(b"cached image")

    image_url, cached = await generator.generate("gothic academy hall", "卡塞尔学院")

    assert image_url == f"/background-assets/{cache_key}.png"
    assert cached is True
    generator.prompt_recorder.record.assert_not_awaited()


def test_siliconflow_prompt_keeps_scene_and_location():
    prompt = BackgroundGenerator._build_prompt("rainy gothic hall", "卡塞尔学院")

    assert "rainy gothic hall" in prompt
    assert "卡塞尔学院" in prompt
    assert "No text" in prompt


@pytest.mark.asyncio
async def test_uncached_background_archives_prompt_without_authorization(
    tmp_path, monkeypatch
):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"b64_json": "aW1hZ2U="}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "app.services.background_generator.httpx.AsyncClient",
        lambda **_kwargs: FakeClient(),
    )
    log_dir = tmp_path / "prompt_logs"
    settings = Settings(
        image_api_key="super-secret-key",
        backgrounds_dir=tmp_path / "backgrounds",
        prompt_logging_enabled=True,
        prompt_log_dir=log_dir,
    )

    _, cached = await BackgroundGenerator(settings).generate(
        "rainy gothic hall", "卡塞尔学院"
    )

    assert cached is False
    payload = json.loads(next(log_dir.rglob("*.json")).read_text(encoding="utf-8"))
    assert payload["purpose"] == "background_image"
    assert payload["api_type"] == "images.generations"
    assert "rainy gothic hall" in payload["request"]["prompt"]
    assert "super-secret-key" not in json.dumps(payload, ensure_ascii=False)
