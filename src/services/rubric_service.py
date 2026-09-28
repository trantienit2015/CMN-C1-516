"""Deterministic rubric loading + the default quality rubric (no LLM)."""

from __future__ import annotations

from typing import Any

# Default rubric — dimension weights must sum to 1.0; threshold drives the verdict.
DEFAULT_RUBRIC: dict[str, Any] = {
    "version": "1.0-default",
    "weights": {
        "anti_slop": 0.35,
        "factual": 0.25,
        "tone": 0.25,
        "completeness": 0.15,
    },
    "thresholds": {"pass": 80, "conditional": 60},
}


def load_rubric(rubric_input: dict[str, Any] | None) -> dict[str, Any]:
    """Validate + normalize a rubric dict; fall back to the default rubric.

    Accepts a caller-provided rubric (already parsed from YAML) or None.
    Ensures weights exist and a version string is present.
    """
    if not rubric_input or not isinstance(rubric_input, dict):
        return dict(DEFAULT_RUBRIC)
    rubric = dict(DEFAULT_RUBRIC)
    rubric.update(rubric_input)
    rubric.setdefault("version", "custom")
    rubric.setdefault("weights", DEFAULT_RUBRIC["weights"])
    rubric.setdefault("thresholds", DEFAULT_RUBRIC["thresholds"])
    return rubric
