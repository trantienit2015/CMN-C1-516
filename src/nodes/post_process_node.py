"""AgentCore Platform v1.0 — CMN-C1-516 post_process node (aggregate + report)."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.aggregate_service import aggregate_quality
from src.services.degradation import NOT_EVALUATED, explain_degradation
from src.services.report_service import build_report
from src.services.state_serde import from_json, to_json

_EXCERPT_MAX = 100


class AggregateReportNode(FunctionNode):
    """Aggregate dimension scores into a weighted 0-100 quality score + verdict,
    then build the structured quality report.

    S-3 output discipline (applied in report_service.build_report):
      * every flagged excerpt is PII-redacted (email / phone / JP マイナンバー)
        before it can reach the report, then
      * deterministically truncated to <= _EXCERPT_MAX chars so the report never
        reproduces a full source passage verbatim.
    """

    # S-1: outer backbone slot — request boundary; matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # ADR-005: composite fields are carried as JSON strings — decode here.
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Preparing the result...",
            metadata={"step": "post_process"},
        )
        # A degraded run produced no quality report by design. The output keeps the
        # documented shape — the runner rejects a successful invocation with no output
        # — and states why. Every value here is a constant: the sentence comes from the
        # allow-listed code, and nothing is read back out of State, so a field the
        # rejected request had already put there cannot reach the caller.
        degraded_code = state.get("error_code", "")
        if degraded_code:
            reason = explain_degradation(degraded_code)
            report = {
                "quality_score": 0,
                "verdict": NOT_EVALUATED,
                "flagged_passages": [],
                "remediation_items": [],
                "rubric_version": "unknown",
                "summary": reason,
                "message": reason,
            }
            emit_trace_event("quality_report_degraded", {"error_code": degraded_code}, state)
            return {
                "quality_score": 0,
                "verdict": NOT_EVALUATED,
                "quality_report_json": to_json(report),
                "formatted_output": reason,
                "result": reason,
                "status": AgentStatus.SUCCESS.value,
            }

        dimension_scores = from_json(state.get("dimension_scores_json"), {})
        rubric = from_json(state.get("rubric_json"), {})
        flagged_spans = from_json(state.get("flagged_spans_json"), [])
        remediation_items = from_json(state.get("remediation_items_json"), [])
        rubric_version = state.get("rubric_version", "unknown")
        validation_error = state.get("validation_error", "")

        agg = aggregate_quality(dimension_scores, rubric)
        verdict = agg["verdict"]
        # If an upstream validation error was recorded, downgrade to CONDITIONAL.
        if validation_error and verdict == "PASS":
            verdict = "CONDITIONAL"

        report = build_report(
            quality_score=agg["quality_score"],
            verdict=verdict,
            flagged_spans=flagged_spans,
            remediation_items=remediation_items,
            rubric_version=rubric_version,
            excerpt_max_chars=_EXCERPT_MAX,
        )

        # message is present on every run so the caller can read one key whatever the
        # outcome; only a degraded run puts a sentence in it.
        report["message"] = ""

        emit_trace_event(
            "quality_report_aggregated",
            {
                "quality_score": agg["quality_score"],
                "verdict": verdict,
                "flagged_spans": len(flagged_spans),
                "rubric_version": rubric_version,
            },
            state,
        )
        return {
            "quality_score": agg["quality_score"],
            "verdict": verdict,
            "quality_report_json": to_json(report),
            "formatted_output": report.get("summary", ""),
            "result": report.get("summary", ""),
            "status": AgentStatus.SUCCESS.value,
        }
