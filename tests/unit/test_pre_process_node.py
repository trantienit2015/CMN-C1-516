# CMN-C1-516 — Unit Tests: ParseRubricNode (pre_process)

import pytest

from framework.schemas.agent_status import AgentStatus
from src.nodes.pre_process_node import ParseRubricNode
from src.services import degradation
from src.services.state_serde import from_json


class TestParseRubricNode:
    def setup_method(self):
        self.node = ParseRubricNode()

    def test_success_parse_and_rubric(self):
        state = {
            "user_input": "# Heading\n\nThis is a sample document body for validation.",
            "input_context": {},
            "node_history": [],
            "error_log": [],
        }
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "Heading" in result["document_body"]
        rubric = from_json(result["rubric_json"], {})
        assert rubric["weights"]
        assert result["rubric_version"]

    # ── Degradation: a rejection the caller can fix ends as SUCCESS + error_code, so
    # the reason survives the runner (a non-SUCCESS result becomes a terminal failure
    # whose text names only the exception type). The document is refused either way.

    @pytest.mark.parametrize("supplied", ["", "  ", "\n\n", "\t"])
    def test_empty_input_degrades(self, supplied):
        state = {"user_input": supplied, "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["error_code"] == degradation.EMPTY_INPUT
        assert result["document_body"] == ""

    def test_oversize_input_degrades(self):
        big = "x" * 60000
        state = {"user_input": big, "input_context": {}, "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["error_code"] == degradation.DOCUMENT_TOO_LARGE
        assert result["document_body"] == ""

    @pytest.mark.parametrize("supplied", ["```\n```", "```py\n```", "```\n\n```"])
    def test_markup_only_document_degrades(self, supplied):
        # Non-empty input whose body is empty once markup is stripped: the caller can
        # fix it, so it degrades here rather than failing in the validation node.
        state = {"user_input": supplied, "input_context": {}, "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["error_code"] == degradation.NO_TEXT_CONTENT

    def test_degraded_result_carries_no_caller_content(self):
        secret = "CONFIDENTIAL_DOCUMENT_TEXT_xyz"
        state = {"user_input": secret * 3000, "input_context": {}, "node_history": [], "error_log": []}
        result = self.node.execute(state)
        assert result["error_code"] == degradation.DOCUMENT_TOO_LARGE
        assert secret not in str(result)
        assert secret not in degradation.explain_degradation(result["error_code"])

    def test_execute_signature(self):
        import inspect

        params = list(inspect.signature(ParseRubricNode.execute).parameters.keys())
        assert params[1] == "state"
        assert "_invoke_impl" not in ParseRubricNode.__dict__
