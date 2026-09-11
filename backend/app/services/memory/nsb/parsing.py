"""Safe type-coercion helpers for NSB LLM output."""


def _safe_str(data: dict, key: str, default: str = "") -> str:
    v = data.get(key, default)
    return str(v) if v is not None else default


def _safe_list(data: dict, key: str) -> list[str]:
    v = data.get(key, [])
    if isinstance(v, list):
        return [str(x) for x in v]
    return []


def _safe_dict(data: dict, key: str) -> dict[str, str]:
    v = data.get(key, {})
    if isinstance(v, dict):
        return {str(k): str(val) for k, val in v.items()}
    return {}


def _safe_float(data: dict, key: str, default: float = 0.5) -> float:
    try:
        return float(data.get(key, default))
    except (TypeError, ValueError):
        return default
