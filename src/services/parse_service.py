"""Deterministic document parsing + language detection (no LLM)."""

from __future__ import annotations

import re

_JP_RANGE = re.compile(r"[぀-ヿ一-鿿]")


def parse_document(raw: str) -> str:
    """Extract the plain-text body from a text/markdown document.

    Strips markdown heading markers and code-fence markers; collapses excess
    blank lines. DOCX binary parsing is out of scope for the deterministic core
    (the caller passes already-extracted text).
    """
    if not raw:
        return ""
    lines = []
    in_fence = False
    for line in raw.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            lines.append(line)
            continue
        lines.append(re.sub(r"^#{1,6}\s+", "", line))
    body = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def detect_language(text: str) -> str:
    """Cheap language detection: 'ja' if Japanese script present, else 'en'."""
    if not text:
        return "unknown"
    jp = len(_JP_RANGE.findall(text))
    return "ja" if jp >= max(5, len(text) * 0.05) else "en"
