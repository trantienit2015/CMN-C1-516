"""AgentCore Platform v1.0 — CMN-C1-516 pre_process node (parse + rubric)."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from shared.services.events import emitter
from shared.services.events.types import EventType
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.degradation import DOCUMENT_TOO_LARGE, EMPTY_INPUT, NO_TEXT_CONTENT
from src.services.parse_service import detect_language, parse_document
from src.services.rubric_service import load_rubric
from src.services.state_serde import to_json

_MAX_BYTES = 51200  # 50KB document size cap (S-1)


class ParseRubricNode(FunctionNode):
    """Validate input, enforce the size cap, parse the document body, detect
    language, and load the quality rubric (deterministic — no LLM).
    """

    # S-1: rubric parsing is a trusted-config operation; require a verified caller
    # rather than the permissive ANONYMOUS framework default.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _degrade(self, code: str, state: dict[str, Any]) -> dict[str, Any]:
        """End a caller-correctable rejection as a degraded success.

        The document is refused either way — nothing reaches the validation
        dimensions. Returning an error instead would reach the caller as a terminal
        failure naming only the exception type, so the reason would never leave the
        audit log. The code is allow-listed and carries no request value, not even
        the document size.
        """
        emit_trace_event("document_rejected", {"reason": code}, state)
        return {"document_body": "", "error_code": code, "status": AgentStatus.SUCCESS.value}

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        # Progress (non-terminal) event for the caller. Outside the Marketplace runtime
        # this resolves to a no-op emitter, so it is safe on every entry path.
        emitter().emit_event(
            event_type=EventType.PROGRESS_UPDATE,
            message="Checking the request...",
            metadata={"step": "pre_process"},
        )
        user_input = state.get("user_input", "")
        input_context = state.get("input_context", {})  # read-only

        if not user_input or not user_input.strip():
            return self._degrade(EMPTY_INPUT, state)

        if len(user_input.encode("utf-8")) > _MAX_BYTES:
            return self._degrade(DOCUMENT_TOO_LARGE, state)

        body = parse_document(user_input)
        if not body:
            # Reachable from a non-empty document: parsing drops markup, so a body of
            # only code fences or heading markers leaves nothing to validate. That is
            # the caller's to fix, so it degrades here rather than failing downstream.
            return self._degrade(NO_TEXT_CONTENT, state)

        language = input_context.get("language") or detect_language(body)
        rubric = load_rubric(input_context.get("rubric"))

        emit_trace_event(
            "rubric_parsed",
            {
                "rubric_version": rubric.get("version", "unknown"),
                "detected_language": language,
                "document_bytes": len(user_input.encode("utf-8")),
            },
            state,
        )
        return {
            "validated_input": body,
            "document_body": body,
            "detected_language": language,
            "rubric_json": to_json(rubric),
            "rubric_version": rubric.get("version", "unknown"),
            "status": AgentStatus.SUCCESS.value,
        }
