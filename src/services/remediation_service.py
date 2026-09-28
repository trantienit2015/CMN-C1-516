"""Per-flag remediation suggestion (<=50 words), constraint-enforced."""

from __future__ import annotations

from typing import Any

_MAX_WORDS = 50

_CATEGORY_HINTS = {
    "generic_filler": "Remove the filler phrase; state the concrete point directly.",
    "vague_claim": "Replace the vague quantifier with a specific figure or cite a source.",
    "repetition": "Delete the duplicated sentence or merge it with the original.",
    "unsupported_claim": "Add a citation or soften the claim to what the evidence supports.",
    "keigo_inconsistency": "Use one register consistently (keep 丁寧語 です/ます throughout).",
}


def suggest_remediations(
    flags: list[dict[str, Any]], llm: Any | None = None, max_words: int = _MAX_WORDS
) -> list[dict[str, Any]]:
    """Return a list of {category, excerpt, suggestion} (each <= max_words)."""
    items: list[dict[str, Any]] = []
    for f in flags:
        category = f.get("category", "general")
        excerpt = f.get("excerpt", "")
        if llm is not None and hasattr(llm, "suggest_fix"):
            suggestion = llm.suggest_fix(category, excerpt)
        else:
            suggestion = _CATEGORY_HINTS.get(category, "Revise this passage for clarity and accuracy.")
        items.append(
            {
                "category": category,
                "excerpt": excerpt,
                "suggestion": _truncate_words(suggestion, max_words),
            }
        )
    return items


def _truncate_words(text: str, max_words: int) -> str:
    words = text.split()
    return text if len(words) <= max_words else " ".join(words[:max_words])
