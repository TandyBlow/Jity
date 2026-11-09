"""world-canonical-v1 byte encoder, independent of game state application.

Callers supply an already schema-normalized projection. This module deliberately
does not infer no-op state changes or implement working-state projection.
"""

import hashlib
import json
import math
from decimal import Decimal

CANONICAL_VERSION = "world-canonical-v1"
MAX_SAFE = 2**53 - 1


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def parse_json(text: str):
    """Preserve numeric precision before safe-integer validation."""
    def bad_constant(value):
        raise ValueError(f"non-finite JSON number: {value}")

    value = json.loads(text, object_pairs_hook=_pairs, parse_float=Decimal, parse_constant=bad_constant)
    canonical_bytes(value)  # Validate Unicode, ASCII keys and all numbers.
    return value


def _string(value: str):
    out = ['"']
    for char in value:
        code = ord(char)
        if 0xD800 <= code <= 0xDFFF:
            raise ValueError("unpaired Unicode surrogate")
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif code < 32:
            out.append(f"\\u{code:04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _encode(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("non-finite number")
        if isinstance(value, Decimal) and not value.is_finite():
            raise ValueError("non-finite number")
        if not -MAX_SAFE <= value <= MAX_SAFE or int(value) != value:
            raise ValueError("expected a safe integer")
        return str(int(value))
    if isinstance(value, list):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) or not key.isascii() for key in value):
            raise ValueError("object keys must be ASCII strings")
        return "{" + ",".join(_string(key) + ":" + _encode(value[key]) for key in sorted(value)) + "}"
    raise ValueError(f"not a JSON value: {type(value).__name__}")


def canonical_bytes(value) -> bytes:
    return _encode(value).encode("utf-8")


def canonical_digest(value) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()
