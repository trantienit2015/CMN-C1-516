"""Tone alignment + Japanese prose (keigo) check.

Keigo static rules are deterministic; tone-vs-audience and naturalness judgment
use an injected LLM when available (deterministic baseline otherwise).
"""

from __future__ import annotations

from typing import Any

# Keigo markers (丁寧語 / 尊敬語 / 謙譲語) — used to detect register mixing.
_TEINEIGO = ("です", "ます", "でした", "ました")
_PLAIN = ("だ。", "である", "だった")


def check_japanese_prose(text: str) -> list[dict[str, Any]]:
    """Deterministic keigo-consistency check: flag mixing 丁寧語 with plain form."""
    flags: list[dict[str, Any]] = []
    has_teinei = any(m in text for m in _TEINEIGO)
    has_plain = any(m in text for m in _PLAIN)
    if has_teinei and has_plain:
        flags.append(
            {
                "category": "keigo_inconsistency",
                "severity": "medium",
                "excerpt": "mixed 丁寧語 (です/ます) and plain form (だ/である) registers",
            }
        )
    return flags


def score_tone(text: str, target_audience: str, language: str, llm: Any | None = None) -> dict[str, Any]:
    """Return {"tone_score": int(0-100), "flagged_spans": [...]}.

    With an LLM, judge tone-vs-audience and Japanese naturalness; otherwise apply
    the deterministic keigo check and a neutral baseline tone score.
    """
    flagged: list[dict[str, Any]] = []
    if language == "ja":
        flagged.extend(check_japanese_prose(text))

    if llm is not None and hasattr(llm, "score_tone"):
        result = llm.score_tone(text, target_audience, language)
        tone_score = int(result.get("tone_score", 75))
        flagged.extend(result.get("flagged_spans", []))
    else:
        # deterministic baseline: penalize per keigo/tonal flag
        tone_score = max(0, 90 - 10 * len(flagged))

    return {"tone_score": tone_score, "flagged_spans": flagged}
