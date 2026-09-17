"""Optional local archive for requests sent to generative model APIs."""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from app.config import Settings

logger = logging.getLogger(__name__)


class PromptRecorder:
    """Write one research-friendly JSON file per logical API request."""

    schema_version = 1

    def __init__(self, settings: Settings) -> None:
        self.enabled = settings.prompt_logging_enabled
        self.output_dir = settings.prompt_log_dir

    async def record(
        self,
        *,
        purpose: str,
        api_type: str,
        model: str,
        service_url: str,
        request: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> Path | None:
        """Archive a request without ever blocking the model call on failure."""
        if not self.enabled:
            return None

        now = datetime.now(timezone.utc)
        record_id = str(uuid4())
        safe_purpose = re.sub(r"[^A-Za-z0-9_-]+", "_", purpose).strip("_") or "unknown"
        filename = f"{now.strftime('%Y%m%dT%H%M%S_%fZ')}_{safe_purpose}_{record_id}.json"
        path = self.output_dir / now.strftime("%Y-%m-%d") / filename
        payload = {
            "schema_version": self.schema_version,
            "record_id": record_id,
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "purpose": purpose,
            "api_type": api_type,
            "model": model,
            "service_url": service_url,
            "context": context or {},
            "request": request,
        }

        try:
            await asyncio.to_thread(self._write_atomically, path, payload)
        except Exception:
            logger.warning("Failed to archive prompt request at %s", path, exc_info=True)
            return None

        logger.info("Prompt archived: %s", path)
        return path

    @staticmethod
    def _write_atomically(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()
