"""Generate and cache atmospheric scene backgrounds."""

import base64
import hashlib
from pathlib import Path

import httpx

from app.config import Settings
from app.services.prompt_recorder import PromptRecorder


class BackgroundGenerationError(RuntimeError):
    pass


class BackgroundGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.prompt_recorder = PromptRecorder(settings)

    async def generate(self, scene_prompt: str, location: str = "") -> tuple[str, bool]:
        if not self.settings.image_api_key:
            raise BackgroundGenerationError(
                "图片生成尚未配置，请设置 IMAGE_API_KEY。"
            )

        prompt = self._build_prompt(scene_prompt, location)
        cache_key = hashlib.sha256(
            f"{self.settings.image_model}\0{self.settings.image_size}\0{prompt}".encode()
        ).hexdigest()
        output_dir = self.settings.backgrounds_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{cache_key}.png"
        if output_file.exists():
            return f"/background-assets/{output_file.name}", True

        endpoint = f"{self.settings.image_base_url.rstrip('/')}/images/generations"
        if self.settings.image_api_provider == "siliconflow":
            payload = {
                "model": self.settings.image_model,
                "prompt": prompt,
                "negative_prompt": "text, caption, logo, watermark, UI, blurry, low quality",
                "image_size": self.settings.image_size,
                "batch_size": 1,
                "num_inference_steps": 28,
                "guidance_scale": 7.5,
            }
        else:
            payload = {
                "model": self.settings.image_model,
                "prompt": prompt,
                "size": self.settings.image_size,
                "n": 1,
            }
        headers = {"Authorization": f"Bearer {self.settings.image_api_key}"}

        await self.prompt_recorder.record(
            purpose="background_image",
            api_type="images.generations",
            model=self.settings.image_model,
            service_url=endpoint,
            request=payload,
            context={"location": location} if location else None,
        )

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                data = result.get("images", []) or result.get("data", [])
                if not data:
                    raise BackgroundGenerationError("图片服务没有返回图片。")
                item = data[0]
                if item.get("b64_json"):
                    image_bytes = base64.b64decode(item["b64_json"])
                elif item.get("url"):
                    image_response = await client.get(item["url"])
                    image_response.raise_for_status()
                    image_bytes = image_response.content
                else:
                    raise BackgroundGenerationError("图片服务返回格式不受支持。")
        except BackgroundGenerationError:
            raise
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise BackgroundGenerationError(f"图片生成失败：{exc}") from exc

        self._write_atomically(output_file, image_bytes)
        return f"/background-assets/{output_file.name}", False

    @staticmethod
    def _build_prompt(scene_prompt: str, location: str) -> str:
        location_hint = f" Location: {location}." if location else ""
        return (
            "Wide cinematic environmental concept art for a dark academy fantasy "
            "interactive story. No text, captions, logos, UI, frames, or watermarks. "
            "Atmospheric lighting, detailed architecture, one single continuous full-bleed "
            "wide landscape scene. No collage, split screen, duplicated view, panels, borders, "
            "or black margins. Leave the center visually calm enough for readable story text."
            f"{location_hint} Scene: {scene_prompt.strip()}"
        )

    @staticmethod
    def _write_atomically(path: Path, content: bytes) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
