# CMN-C1-516 — Unit Tests: QualityValidationNode (main)

from framework.schemas.agent_status import AgentStatus
from src.nodes.main_node import QualityValidationNode
from src.services.state_serde import from_json, to_json


class TestQualityValidationNode:
    def setup_method(self):
        self.node = QualityValidationNode()

    def _state(self, body, language="en"):
        # ADR-005: rubric is carried as a JSON string in State.
        return {
            "document_body": body,
            "detected_language": language,
            "input_context": {"target_audience": "executive"},
            "rubric_json": to_json(
                {"weights": {"anti_slop": 0.35, "factual": 0.25, "tone": 0.25, "completeness": 0.15}}
            ),
            "node_history": [],
            "error_log": [],
            "trace_id": "t",
            "correlation_id": "c",
            "session_id": "s",
        }

    def test_success_flags_slop(self):
        body = (
            "In conclusion, it is important to note that various experts leverage synergy "
            "to navigate the complexities of the modern enterprise landscape and deliver value."
        )
        result = self.node.execute(self._state(body))
        assert result["status"] == AgentStatus.SUCCESS.value
        flagged = from_json(result["flagged_spans_json"], [])
        scores = from_json(result["dimension_scores_json"], {})
        remediation = from_json(result["remediation_items_json"], [])
        assert len(flagged) >= 1
        assert set(scores.keys()) == {"anti_slop", "factual", "tone", "completeness"}
        assert len(remediation) == len(flagged)

    def test_clean_document_few_flags(self):
        body = (
            "The Q3 revenue was 12.4 million USD, up 8 percent over Q2 per the audited statement [1]. "
            "Headcount grew from 220 to 245 in the same period across three regional offices."
        )
        result = self.node.execute(self._state(body))
        assert result["status"] == AgentStatus.SUCCESS.value
        scores = from_json(result["dimension_scores_json"], {})
        assert scores["anti_slop"] >= 80

    def test_empty_body_errors(self):
        # No degradation code and nothing to validate = internally inconsistent
        # pipeline, not a caller mistake. This must keep failing.
        result = self.node.execute(self._state(""))
        assert result["status"] == AgentStatus.ERROR.value

    def test_degraded_run_skips_validation(self):
        state = self._state("")
        state["error_code"] = "EMPTY_INPUT"
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert from_json(result["flagged_spans_json"], None) == []
        assert from_json(result["dimension_scores_json"], None) == {}
        assert result["unsupported_claims"] == []
        assert "error_log" not in result

    def test_degraded_run_never_reaches_the_dimensions(self, monkeypatch):
        # Not merely "produces no findings" — the validation must not run at all. A
        # body is still in State here (a rejection can happen after parsing), so the
        # guard, not the emptiness of the body, is what has to stop it.
        def _fail(*args, **kwargs):
            raise AssertionError("detect_sloppiness reached on a degraded run")

        monkeypatch.setattr("src.nodes.main_node.detect_sloppiness", _fail)
        state = self._state("A document body that would otherwise be validated.")
        state["error_code"] = "NO_TEXT_CONTENT"
        assert self.node.execute(state)["status"] == AgentStatus.SUCCESS.value

    def test_japanese_keigo_inconsistency_flagged(self):
        body = "本提案は重要です。導入する。効果が高いである。"
        result = self.node.execute(self._state(body, language="ja"))
        flagged = from_json(result["flagged_spans_json"], [])
        cats = [f["category"] for f in flagged]
        assert "keigo_inconsistency" in cats
