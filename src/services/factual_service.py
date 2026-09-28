"""Factual consistency check against an optional reference KB."""

from __future__ import annotations

import re
from typing import Any


def check_factual_consistency(text: str, retriever: Any | None = None, top_k: int = 5) -> dict[str, Any]:
    """Cross-check assertions against a reference KB when available.

    If ``retriever`` is injected (exposing ``search(query, top_k) -> list[dict]``),
    each candidate claim is checked for support. Without a KB, candidate
    unsupported assertions are flagged heuristically (statements with strong
    quantitative/absolute markers but no citation).

    Returns {"unsupported_claims": [...], "flagged_spans": [...]}.
    """
    claims = _extract_claims(text)
    unsupported: list[str] = []
    flagged: list[dict[str, Any]] = []

    for claim in claims:
        if retriever is not None:
            hits = retriever.search(claim, top_k=top_k)
            if not hits:
                unsupported.append(claim)
                flagged.append({"category": "unsupported_claim", "severity": "high", "excerpt": claim})
        else:
            # No KB: flag absolute/quantitative claims lacking any citation marker.
            if _looks_unsupported(claim):
                unsupported.append(claim)
                flagged.append({"category": "unsupported_claim", "severity": "medium", "excerpt": claim})

    return {"unsupported_claims": unsupported, "flagged_spans": flagged}


_ABSOLUTE = re.compile(r"\b(\d+%|always|never|all|every|guaranteed|最も|必ず|全て)\b", re.IGNORECASE)
_CITATION = re.compile(r"(\[\d+\]|https?://|出典|参照|according to)", re.IGNORECASE)


def _extract_claims(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?。\n]", text) if len(s.strip()) > 20]


def _looks_unsupported(claim: str) -> bool:
    return bool(_ABSOLUTE.search(claim)) and not _CITATION.search(claim)
