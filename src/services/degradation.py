"""Caller-facing wording for a degraded run.

A rejection the caller can act on — an empty document, one over the size cap, or
one whose body is empty after parsing — ends as SUCCESS carrying an ``error_code``
and an empty quality report, rather than as a failure. The reason therefore has to
travel in the output itself: the runner turns a non-SUCCESS result into a terminal
failure whose text names only the exception type, so a caller who sent an unusable
document would learn nothing about what to change.

Each sentence names what to send instead. No request value is ever interpolated —
not the document, not its size, not the offending line — so the message cannot echo
caller content back into the output. The code is an allow-listed token the node
computes for its audit event.

Two rejections deliberately do not come here. An internally inconsistent run (no
code set and still nothing to validate) keeps returning status=ERROR, because it is
a defect rather than a caller mistake. A framework security gate refusal likewise
stays a failure: explaining which pattern tripped it would tell the sender how to
get past it.
"""

from __future__ import annotations

EMPTY_INPUT = "EMPTY_INPUT"
DOCUMENT_TOO_LARGE = "DOCUMENT_TOO_LARGE"
NO_TEXT_CONTENT = "NO_TEXT_CONTENT"

# Verdict slot of a degraded report. The report keys stay present so the output
# shape does not change with the outcome, and this value says why no verdict is
# given — no validation ran, as opposed to validation that ran and passed.
NOT_EVALUATED = "NOT_EVALUATED"

_MESSAGES: dict[str, str] = {
    EMPTY_INPUT: (
        "No document was received. Send the text of the document to validate — a "
        "proposal, report, email or contract, as plain text or markdown."
    ),
    DOCUMENT_TOO_LARGE: (
        "The document is larger than this deployment accepts. Send a smaller "
        "document, or split it and validate each part separately; the size cap is "
        "part of the deployment configuration."
    ),
    NO_TEXT_CONTENT: (
        "The document holds no text to validate once markup is removed. Send a "
        "document whose body carries prose, not only code fences or heading markers."
    ),
}

_FALLBACK = "The document could not be accepted and no quality report was produced."


def explain_degradation(code: str) -> str:
    """Return one caller-facing sentence for a degradation code."""
    return _MESSAGES.get(code, f"{_FALLBACK} [{code}]" if code else _FALLBACK)
