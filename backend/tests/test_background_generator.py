"""Tests for cached AI scene backgrounds."""

import hashlib

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
    prompt = generator._build_prompt("gothic academy hall", "卡塞尔学院")
    cache_key = hashlib.sha256(
        f"{settings.image_model}\0{settings.image_size}\0{prompt}".encode()
    ).hexdigest()
    cached_file = tmp_path / f"{cache_key}.png"
    cached_file.write_bytes(b"cached image")

    image_url, cached = await generator.generate("gothic academy hall", "卡塞尔学院")

    assert image_url == f"/background-assets/{cache_key}.png"
    assert cached is True


def test_siliconflow_prompt_keeps_scene_and_location():
    prompt = BackgroundGenerator._build_prompt("rainy gothic hall", "卡塞尔学院")

    assert "rainy gothic hall" in prompt
    assert "卡塞尔学院" in prompt
    assert "No text" in prompt
