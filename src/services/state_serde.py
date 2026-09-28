"""ADR-005 State serde — JSON (de)serialization for composite payloads.

LangGraph checkpoints use msgpack; nested ``dict`` / ``list[dict]`` State fields
risk silent corruption on serialization. ADR-005 therefore requires composite
payloads to be carried across State as JSON ``str`` (a primitive) and (de)coded
at the node boundary. These helpers are the single, tested encode/decode point.

This follows the ADR-005 remediation pattern.
"""

from __future__ import annotations

import json
from typing import Any


def to_json(value: Any) -> str:
    """Serialize a JSON-safe value to a compact string for State storage.

    ``ensure_ascii=False`` keeps Japanese (CJK) text readable rather than
    escaping it to ``\\uXXXX`` sequences.
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def from_json(raw: str | None, default: Any = None) -> Any:
    """Deserialize a JSON string written by :func:`to_json`.

    Returns ``default`` for ``None`` / empty / malformed input so a missing or
    corrupted field never raises inside ``execute()``.
    """
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default
