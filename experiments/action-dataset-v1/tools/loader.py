"""Bridge to the loader's frozen serializer (04's `action-next-step-x1`).

The dataset must not carry a second text serializer: training input is whatever
`worktrees/04-settlement/experiments/action-next-step/serialize.py` renders.
This module imports that file read-only, records its sha256, and refuses to
pretend a missing or different serializer is fine.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

DEFAULT_SERIALIZER = Path(
    "D:/others/Jity/.local/parallel-local-game/worktrees/04-settlement/experiments/action-next-step/serialize.py"
)


class LoaderError(RuntimeError):
    """Raised when the loader serializer is missing or unusable."""


def load_serializer(path: Path = DEFAULT_SERIALIZER) -> ModuleType:
    path = Path(path)
    if not path.is_file():
        raise LoaderError(f"loader serializer not found: {path}")
    spec = importlib.util.spec_from_file_location("action_next_step_serialize", path)
    if spec is None or spec.loader is None:
        raise LoaderError(f"cannot load loader serializer: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("action_next_step_serialize", module)
    spec.loader.exec_module(module)
    return module


def render_row(module: ModuleType, row: dict[str, Any]) -> dict[str, Any]:
    try:
        text = module.render_x(row)
        ids = module.candidate_ids(row)
    except Exception as error:  # noqa: BLE001 - the caller reports it
        raise LoaderError(f"{row.get('rowId', '?')}: loader serializer rejected the row: {error}") from error
    return {
        "text": text,
        "chars": len(text),
        "candidateIds": ids,
        "serializerVersion": getattr(module, "SERIALIZER_VERSION", "unknown"),
        "serializerSha256": module.serializer_digest(),
    }


def object_index(module: ModuleType, row: dict[str, Any], step: dict[str, Any]) -> int:
    return module.object_index(row, step)
