# CMN-C1-516 — Unit Tests: deterministic services

from src.services.aggregate_service import aggregate_quality, dimension_score_from_flags
from src.services.parse_service import detect_language, parse_document
from src.services.report_service import redact_pii
from src.services.rubric_service import DEFAULT_RUBRIC, load_rubric
from src.services.slop_service import detect_sloppiness
from src.services.state_serde import from_json, to_json


def test_parse_strips_markdown():
    body = parse_document("# Title\n\n```\ncode\n```\n\nBody text here.")
    assert "Title" in body and "Body text" in body


def test_detect_language_ja():
    assert detect_language("これは日本語の文書です。とても重要です。") == "ja"
    assert detect_language("This is an English document.") == "en"


def test_load_rubric_default_and_custom():
    assert load_rubric(None)["version"] == DEFAULT_RUBRIC["version"]
    custom = load_rubric({"version": "v2", "thresholds": {"pass": 90, "conditional": 70}})
    assert custom["version"] == "v2"
    assert custom["weights"]  # back-filled from default


def test_aggregate_verdicts():
    rubric = DEFAULT_RUBRIC
    high = aggregate_quality({"anti_slop": 95, "factual": 95, "tone": 95, "completeness": 95}, rubric)
    assert high["verdict"] == "PASS"
    low = aggregate_quality({"anti_slop": 10, "factual": 10, "tone": 10, "completeness": 10}, rubric)
    assert low["verdict"] == "FAIL"


def test_dimension_score_penalty():
    flags = [{"severity": "high"}, {"severity": "medium"}]
    assert dimension_score_from_flags(flags) == 100 - 25 - 12


def test_pb_slop_filler_flagged():
    # PB-SLOP-001: known AI-tell filler MUST be flagged (deterministic baseline).
    flags = detect_sloppiness("In conclusion, it is important to note that we leverage synergy.")
    cats = [f["category"] for f in flags]
    assert "generic_filler" in cats


# --- ADR-005 state serde -------------------------------------------------

def test_state_serde_roundtrip():
    payload = {"weights": {"anti_slop": 0.35}, "list": [{"a": 1}], "jp": "日本語"}
    encoded = to_json(payload)
    assert isinstance(encoded, str)  # primitive carried across State
    assert from_json(encoded) == payload
    # CJK is preserved literally, not \uXXXX-escaped
    assert "日本語" in encoded


def test_state_serde_handles_missing_and_malformed():
    assert from_json(None, {}) == {}
    assert from_json("", []) == []
    assert from_json("{not json", {"fallback": True}) == {"fallback": True}


# --- S-3 PII redaction ---------------------------------------------------

def test_redact_pii_email_phone_mynumber():
    raw = "Mail a@b.co.jp call 090-1234-5678 mynum 123456789012"
    out = redact_pii(raw)
    assert "a@b.co.jp" not in out
    assert "090-1234-5678" not in out
    assert "123456789012" not in out
    assert "[REDACTED_EMAIL]" in out
    assert "[REDACTED_MYNUMBER]" in out


def test_redact_pii_keeps_clean_text():
    clean = "The Q3 revenue grew by eight percent over the prior quarter."
    assert redact_pii(clean) == clean


def test_redact_pii_is_linear_on_adversarial_input():
    # ReDoS regression: with an unbounded email quantifier, a failed match on a
    # 50KB run of local-part characters took ~2s (quadratic). Bounded quantifiers
    # keep it linear; the input size equals the pre_process 50KB document cap.
    import time

    for raw in ("a" * 51200, "a@" + "b" * 51198):
        start = time.perf_counter()
        redact_pii(raw)
        assert time.perf_counter() - start < 0.5


def test_redact_pii_email_still_masked_with_bounds():
    out = redact_pii("contact first.last+tag@mail.example.co.jp today")
    assert "[REDACTED_EMAIL]" in out
    assert "example" not in out


class TestDegradation:
    def test_every_code_has_its_own_sentence(self):
        from src.services import degradation

        codes = [degradation.EMPTY_INPUT, degradation.DOCUMENT_TOO_LARGE, degradation.NO_TEXT_CONTENT]
        sentences = [degradation.explain_degradation(c) for c in codes]
        assert all(sentences)
        assert len(set(sentences)) == len(codes)

    def test_unknown_and_empty_codes_still_explain_themselves(self):
        from src.services import degradation

        assert "SOME_NEW_CODE" in degradation.explain_degradation("SOME_NEW_CODE")
        assert degradation.explain_degradation("")

    def test_no_sentence_carries_a_request_value(self):
        # The wording is derived from the code alone — no document text, no size, no
        # line position. A format placeholder would mean the opposite.
        from src.services import degradation

        for code, text in degradation._MESSAGES.items():
            assert "{" not in text and "%" not in text, code
