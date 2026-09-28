"""AgentCore Platform v1.0 — CMN-C1-516 main node (quality validation)."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.aggregate_service import dimension_score_from_flags
from src.services.factual_service import check_factual_consistency
from src.services.remediation_service import suggest_remediations
from src.services.slop_service import detect_sloppiness
from src.services.state_serde import to_json
from src.services.tone_service import score_tone


class QualityValidationNode(FunctionNode):
    """Run the four LLM-reasoning validation dimensions (anti-slop, factual, tone/
    keigo, completeness signal) over the document, produce dimension scores +
    flagged spans, and generate per-flag remediation suggestions.
    """

    # S-1: outer backbone slot — request boundary; matches agent.yaml required_trust_level.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(
        self, llm: Any | None = None, retriever: Any | None = None, top_k: int = 5, max_remediation_words: int = 50
    ):
        self._llm = llm
        self._retriever = retriever
        self._top_k = top_k
        self._max_remediation_words = max_remediation_words

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Working on the request...",
            metadata={"step": "main"},
        )
        body = state.get("document_body", "")
        language = state.get("detected_language", "en")
        input_context = state.get("input_context", {})
        target_audience = input_context.get("target_audience", "general")

        # A degraded run carries the reason the caller can act on. The validation is
        # skipped exactly as it is on the error path below; the difference is only
        # that the run stays SUCCESS so the reason reaches the caller.
        degraded_code = state.get("error_code", "")
        if degraded_code:
            emit_trace_event("validation_skipped", {"reason": degraded_code}, state)
            return {
                "flagged_spans_json": to_json([]),
                "unsupported_claims": [],
                "dimension_scores_json": to_json({}),
                "remediation_items_json": to_json([]),
                "status": AgentStatus.SUCCESS.value,
            }

        if not body:
            # No degradation code and still nothing to validate means the pipeline is
            # internally inconsistent, not that the caller sent an unusable document —
            # the caller has nothing to correct here, so this keeps failing.
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": ["QualityValidationNode: no document_body to validate"],
            }

        # Dimension 1 — anti-slop
        slop_flags = detect_sloppiness(body, llm=self._llm)
        # Dimension 2 — factual consistency
        factual = check_factual_consistency(body, retriever=self._retriever, top_k=self._top_k)
        factual_flags = factual["flagged_spans"]
        # Dimension 3 — tone + Japanese prose
        tone = score_tone(body, target_audience, language, llm=self._llm)
        tone_flags = tone["flagged_spans"]
        # Dimension 4 — completeness (heuristic: penalize very short docs)
        completeness_score = 100 if len(body) >= 200 else max(40, len(body) // 2)

        all_flags = list(slop_flags) + list(factual_flags) + list(tone_flags)

        dimension_scores = {
            "anti_slop": dimension_score_from_flags(slop_flags),
            "factual": dimension_score_from_flags(factual_flags),
            "tone": tone["tone_score"],
            "completeness": completeness_score,
        }

        remediation = suggest_remediations(all_flags, llm=self._llm, max_words=self._max_remediation_words)

        emit_trace_event(
            "content_quality_validated",
            {
                "flag_count": len(all_flags),
                "dimensions": list(dimension_scores.keys()),
                "language": language,
            },
            state,
        )

        return {
            "flagged_spans_json": to_json(all_flags),
            "unsupported_claims": factual["unsupported_claims"],
            "dimension_scores_json": to_json(dimension_scores),
            "remediation_items_json": to_json(remediation),
            "status": AgentStatus.SUCCESS.value,
        }
