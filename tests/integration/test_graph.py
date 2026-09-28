# CMN-C1-516 — Integration Tests: full graph compile + invoke (Cat 1)

from framework.schemas.agent_status import AgentStatus
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from src.graph.graph import Graph
from src.services import degradation


def _ctx():
    return InvocationContext(
        session_id="it-1",
        caller_trust_level=TrustLevel.VERIFIED_EXTERNAL,
        caller_id="tester",
    )


class TestGraphIntegration:
    def test_full_pipeline_success(self):
        agent = Graph()
        agent.compile()
        doc = (
            "In conclusion, it is important to note that various experts leverage synergy. "
            "This guarantees 100% success always."
        )
        result = agent.invoke(doc, ctx=_ctx())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert not isinstance(result["status"], AgentStatus)
        assert len(result.get("node_history", [])) >= 5
        # get_output() decodes the JSON report back to a dict at the output boundary.
        out = result.get("output")
        assert isinstance(out, dict)
        assert out["verdict"] in ("PASS", "CONDITIONAL", "FAIL")
        assert "quality_score" in out

    def test_empty_input_degrades_instead_of_failing(self):
        # End-to-end shape of a caller-correctable rejection: the run completes, the
        # backbone still runs to the end, and the reason is in the output. A
        # non-SUCCESS result would reach the caller as a terminal failure naming only
        # the exception type, with the reason left in the audit log.
        agent = Graph()
        agent.compile()
        result = agent.invoke("", ctx=_ctx())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert not isinstance(result["status"], AgentStatus)
        assert len(result.get("node_history", [])) >= 5
        out = result.get("output")
        assert isinstance(out, dict)
        assert out["verdict"] == degradation.NOT_EVALUATED
        assert out["quality_score"] == 0
        assert out["flagged_passages"] == []
        assert out["message"] == degradation.explain_degradation(degradation.EMPTY_INPUT)

    def test_markup_only_document_degrades(self):
        agent = Graph()
        agent.compile()
        result = agent.invoke("```\n```", ctx=_ctx())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert not isinstance(result["status"], AgentStatus)
        assert result["output"]["message"] == degradation.explain_degradation(degradation.NO_TEXT_CONTENT)

    def test_degraded_output_never_echoes_the_document(self):
        agent = Graph()
        agent.compile()
        secret = "CONFIDENTIAL_DOCUMENT_TEXT_xyz"
        result = agent.invoke(secret * 3000, ctx=_ctx())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert not isinstance(result["status"], AgentStatus)
        assert secret not in str(result["output"])

    def test_success_path_carries_an_empty_message(self):
        agent = Graph()
        agent.compile()
        result = agent.invoke("Q3 revenue reached 12.4 million USD per the audited statement [1].", ctx=_ctx())
        assert result["output"]["message"] == ""

    def test_clean_document_scores_higher(self):
        agent = Graph()
        agent.compile()
        doc = (
            "Q3 revenue reached 12.4 million USD per the audited statement [1]. "
            "Headcount grew from 220 to 245 across three regional offices in the same period."
        )
        result = agent.invoke(doc, ctx=_ctx())
        out = result.get("output")
        assert isinstance(out, dict)
        assert out["quality_score"] >= 50
