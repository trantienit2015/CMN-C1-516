"""Deterministic quality aggregation: weighted score + verdict (no LLM)."""

from __future__ import annotations

from typing import Any


def aggregate_quality(dimension_scores: dict[str, Any], rubric: dict[str, Any]) -> dict[str, Any]:
    """Compute a weighted 0-100 score and a PASS/CONDITIONAL/FAIL verdict.

    dimension_scores: {anti_slop, factual, tone, completeness} each 0-100.
    rubric: must contain weights (summing ~1.0) and thresholds {pass, conditional}.
    """
    weights = rubric.get("weights", {})
    thresholds = rubric.get("thresholds", {"pass": 80, "conditional": 60})

    total_weight = sum(weights.values()) or 1.0
    score = 0.0
    for dim, w in weights.items():
        score += float(dimension_scores.get(dim, 0)) * (w / total_weight)
    score_int = round(score)

    if score_int >= thresholds.get("pass", 80):
        verdict = "PASS"
    elif score_int >= thresholds.get("conditional", 60):
        verdict = "CONDITIONAL"
    else:
        verdict = "FAIL"

    return {"quality_score": score_int, "verdict": verdict}


def dimension_score_from_flags(flags: list[dict[str, Any]], base: int = 100) -> int:
    """Map a flag list to a 0-100 dimension score (severity-weighted penalty)."""
    penalty = {"high": 25, "medium": 12, "low": 5}
    score = base
    for f in flags:
        score -= penalty.get(f.get("severity", "low"), 5)
    return max(0, score)
