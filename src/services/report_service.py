"""Quality report assembly + S-3 output discipline.

S-3 (output security gate) is applied here, at the only boundary where source
excerpts reach the caller-facing report:

  1. PII redaction: email / phone / Japanese マイナンバー patterns
     in every flagged excerpt are masked BEFORE the report is built. Length
     truncation alone is not redaction — a 100-char excerpt can still leak a full
     email address or phone number.
  2. Excerpt truncation: each redacted excerpt is truncated to <= excerpt_max_chars
     so the report never reproduces a full source passage verbatim.

PII patterns are deterministic regexes with bounded quantifiers only (an
unbounded `+` / `{n,}` makes a failed match quadratic in the input length).
"""

from __future__ import annotations

import re
from typing import Any

_EXCERPT_MAX = 100

# --- S-3 PII patterns (deterministic) -------------------------------------
# RFC 5321 / 1035 length bounds: local part <= 64, domain <= 253, TLD label <= 63.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,253}\.[A-Za-z]{2,63}")
# International + JP phone numbers (e.g. +81 90-1234-5678, 03-1234-5678, 090 1234 5678)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[-\s]?)?(?:\d{2,4}[-\s]?){2,4}\d{2,4}(?!\d)")
# Japanese My Number (マイナンバー) — 12 contiguous digits
_MYNUMBER_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")

_EMAIL_MASK = "[REDACTED_EMAIL]"
_PHONE_MASK = "[REDACTED_PHONE]"
_MYNUMBER_MASK = "[REDACTED_MYNUMBER]"


def redact_pii(text: str) -> str:
    """Mask email / phone / My Number occurrences in a free-text string.

    Order matters: My Number (12 digits) and email are masked before the looser
    phone pattern so a phone regex does not partially consume them.
    """
    if not text:
        return text
    text = _EMAIL_RE.sub(_EMAIL_MASK, text)
    text = _MYNUMBER_RE.sub(_MYNUMBER_MASK, text)
    text = _PHONE_RE.sub(_PHONE_MASK, text)
    return text


def build_report(
    quality_score: int,
    verdict: str,
    flagged_spans: list[dict[str, Any]],
    remediation_items: list[dict[str, Any]],
    rubric_version: str,
    excerpt_max_chars: int = _EXCERPT_MAX,
) -> dict[str, Any]:
    """Build the structured quality report.

    S-3 discipline: every flagged/remediation excerpt is PII-redacted, then
    deterministically truncated to <= excerpt_max_chars.
    """
    flagged = [_sanitize_excerpt(f, excerpt_max_chars) for f in flagged_spans]
    remediation = [_sanitize_excerpt(r, excerpt_max_chars) for r in remediation_items]

    summary = f"{verdict}: quality score {quality_score}/100 with " f"{len(flagged)} flagged passage(s)."

    return {
        "quality_score": quality_score,
        "verdict": verdict,
        "flagged_passages": flagged,
        "remediation_items": remediation,
        "rubric_version": rubric_version,
        "summary": summary,
    }


def _sanitize_excerpt(item: dict[str, Any], limit: int) -> dict[str, Any]:
    """Apply S-3 to a span dict: redact PII in any user-text field, then truncate.

    Both ``excerpt`` (raw source text) and ``text`` (alternate key used by some
    LLM detectors) are sanitized so no source field leaks verbatim PII.
    """
    out = dict(item)
    for key in ("excerpt", "text"):
        val = out.get(key)
        if isinstance(val, str):
            redacted = redact_pii(val)
            if len(redacted) > limit:
                redacted = redacted[:limit] + "…"
            out[key] = redacted
    return out
