"""Semantic anti-slop detection (LLM-driven, deterministic fallback).

Four categories: circular reasoning, generic filler, vague/unsupported claims,
repetition. When an LLM is injected it does the semantic detection; otherwise a
deterministic keyword/heuristic pass provides a runnable baseline.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

# Deterministic AI-tell markers per category (baseline when no LLM is configured).
_FILLER = (
    "in today's fast-paced world",
    "it is important to note",
    "in conclusion",
    "delve into",
    "navigate the complexities",
    "leverage",
    "synergy",
    "上記の通り",
    "言うまでもなく",
)
_VAGUE = ("various", "numerous", "a number of", "many experts", "studies show", "様々な", "多くの")


def detect_sloppiness(text: str, llm: Any | None = None) -> list[dict[str, Any]]:
    """Return a list of flagged-span dicts: {category, severity, excerpt}."""
    if llm is not None:
        return llm_detect(text, llm)

    flags: list[dict[str, Any]] = []
    lower = text.lower()
    for phrase in _FILLER:
        if phrase in lower:
            flags.append({"category": "generic_filler", "severity": "medium", "excerpt": phrase})
    for phrase in _VAGUE:
        if phrase in lower:
            flags.append({"category": "vague_claim", "severity": "low", "excerpt": phrase})
    # crude repetition: same sentence appearing twice
    sentences = [s.strip() for s in re.split(r"[.!?。]", text) if s.strip()]
    seen: set[str] = set()
    for s in sentences:
        key = s.lower()
        if key in seen and len(s) > 20:
            flags.append({"category": "repetition", "severity": "medium", "excerpt": s})
        seen.add(key)
    return flags


class SlopDetector(Protocol):
    """Surface the injected client must expose.

    Either entry point is accepted; the caller picks whichever the client has.
    """

    def detect_slop(self, text: str) -> list[dict[str, Any]]: ...

    def complete(self, messages: list[dict[str, str]]) -> Any: ...


def llm_detect(text: str, llm: "SlopDetector") -> list[dict[str, Any]]:
    """Delegate semantic detection to an injected LLM client.

    The LLM client must expose ``detect_slop(text) -> list[dict]`` or ``complete(messages)``.
    """
    if hasattr(llm, "detect_slop"):
        return llm.detect_slop(text)
    # Fallback: ask via complete() and expect a JSON-ish list; keep robust.
    raw = llm.complete(
        [{"role": "user", "content": f"List anti-slop issues (category, severity, excerpt) in:\n{text}"}]
    )
    return raw if isinstance(raw, list) else []
