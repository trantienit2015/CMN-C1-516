# CMN-C1-516 — Unit Tests: AggregateReportNode (post_process)

from framework.schemas.agent_status import AgentStatus
from src.nodes.post_process_node import AggregateReportNode
from src.services import degradation
from src.services.state_serde import from_json, to_json


class TestAggregateReportNode:
    def setup_method(self):
        self.node = AggregateReportNode()

    def _state(self, scores, extra=None, flagged=None):
        # ADR-005: composite inputs are carried as JSON strings in State.
        s = {
            "dimension_scores_json": to_json(scores),
            "rubric_json": to_json({
                "version": "1.0-default",
                "weights": {"anti_slop": 0.35, "factual": 0.25, "tone": 0.25, "completeness": 0.15},
                "thresholds": {"pass": 80, "conditional": 60},
            }),
            "flagged_spans_json": to_json(
                flagged
                if flagged is not None
                else [{"category": "vague_claim", "severity": "low", "excerpt": "x" * 200}]
            ),
            "remediation_items_json": to_json(
                [{"category": "vague_claim", "excerpt": "x", "suggestion": "be specific"}]
            ),
            "rubric_version": "1.0-default",
            "node_history": [],
            "error_log": [],
        }
        if extra:
            s.update(extra)
        return s

    def _report(self, result):
        return from_json(result["quality_report_json"], {})

    def test_pass_verdict(self):
        result = self.node.execute(self._state({"anti_slop": 95, "factual": 90, "tone": 90, "completeness": 100}))
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["verdict"] == "PASS"
        assert result["quality_score"] >= 80

    def test_fail_verdict(self):
        result = self.node.execute(self._state({"anti_slop": 20, "factual": 30, "tone": 40, "completeness": 50}))
        assert result["verdict"] == "FAIL"

    def test_excerpt_truncated_to_100(self):
        result = self.node.execute(self._state({"anti_slop": 95, "factual": 90, "tone": 90, "completeness": 100}))
        excerpt = self._report(result)["flagged_passages"][0]["excerpt"]
        assert len(excerpt) <= 101  # 100 + ellipsis char

    def test_validation_error_downgrades_pass(self):
        result = self.node.execute(
            self._state(
                {"anti_slop": 95, "factual": 90, "tone": 90, "completeness": 100},
                extra={"validation_error": "partial parse failure"},
            )
        )
        assert result["verdict"] == "CONDITIONAL"

    def test_pii_redacted_in_flagged_excerpt(self):
        """Email / phone in a flagged excerpt must be masked, not
        merely truncated, in the report output."""
        flagged = [{
            "category": "unsupported_claim",
            "severity": "high",
            "excerpt": "Contact taro.yamada@example.co.jp or 090-1234-5678 for details.",
        }]
        result = self.node.execute(
            self._state({"anti_slop": 95, "factual": 90, "tone": 90, "completeness": 100}, flagged=flagged)
        )
        excerpt = self._report(result)["flagged_passages"][0]["excerpt"]
        assert "taro.yamada@example.co.jp" not in excerpt
        assert "090-1234-5678" not in excerpt
        assert "[REDACTED_EMAIL]" in excerpt
        assert "[REDACTED_PHONE]" in excerpt

    # ── Degradation: no validation ran, but the runner rejects a successful
    # invocation with no output, so the documented shape is emitted with the reason.

    def test_degraded_output_keeps_the_contract_shape(self):
        state = self._state({"anti_slop": 90, "factual": 90, "tone": 90, "completeness": 90})
        state["error_code"] = degradation.NO_TEXT_CONTENT
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["quality_score"] == 0
        assert result["verdict"] == degradation.NOT_EVALUATED
        report = from_json(result["quality_report_json"], {})
        normal = from_json(
            self.node.execute(self._state({"anti_slop": 90, "factual": 90, "tone": 90, "completeness": 90}))[
                "quality_report_json"
            ],
            {},
        )
        assert set(report) == set(normal)  # same key set whatever the outcome
        assert report["message"] == degradation.explain_degradation(degradation.NO_TEXT_CONTENT)
        assert result["formatted_output"] == report["message"]

    def test_normal_report_carries_an_empty_message(self):
        result = self.node.execute(self._state({"anti_slop": 90, "factual": 90, "tone": 90, "completeness": 90}))
        assert from_json(result["quality_report_json"], {})["message"] == ""

    def test_degraded_output_ignores_state_leftovers(self):
        # The rejected request had already put values in State. None may surface: the
        # degraded report is built from constants only.
        state = self._state(
            {"anti_slop": 90, "factual": 90, "tone": 90, "completeness": 90},
            flagged=[{"category": "vague_claim", "severity": "low", "excerpt": "LEFTOVER_EXCERPT_xyz"}],
        )
        state["error_code"] = degradation.EMPTY_INPUT
        result = self.node.execute(state)
        assert "LEFTOVER_EXCERPT_xyz" not in str(result)
        report = from_json(result["quality_report_json"], {})
        assert report["flagged_passages"] == [] and report["remediation_items"] == []

    def test_unknown_code_still_explains_itself(self):
        state = self._state({"anti_slop": 90, "factual": 90, "tone": 90, "completeness": 90})
        state["error_code"] = "SOME_NEW_CODE"
        assert self.node.execute(state)["formatted_output"]
