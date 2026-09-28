"""AgentCore Platform v1.0 — CMN-C1-516 state schema."""

# ADR-005: State must be a flat TypedDict of msgpack-safe primitives — never a
# Pydantic BaseModel, and never a nested dict / list[dict]. LangGraph checkpoints
# use msgpack serialization; composite/nested objects risk silent corruption.
# Composite payloads (rubric, flagged_spans, dimension_scores, remediation_items,
# quality_report) are therefore carried as JSON strings and (de)coded at the node
# boundary via src.services.state_serde (to_json / from_json).
# This follows the ADR-005 remediation pattern.
# Do NOT add credentials, secrets, or Pydantic models.

from typing import NotRequired, Optional

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Content quality validation state.

    All shared fields (user_input, status, session_id, node_history, error_log,
    validated_input, hitl_*, etc.) are inherited from AgentState. Only
    validation-specific fields below — flat, JSON-serializable primitives only.

    Composite fields are JSON strings (ADR-005): decode with
    ``state_serde.from_json`` on read, encode with ``state_serde.to_json`` on write.
    """

    # Degradation marker. A rejection the caller can act on (empty document, one
    # over the size cap, one with no text after parsing) ends the run as SUCCESS
    # carrying this code and an empty quality report, so the caller is told why
    # instead of receiving a bare terminal failure. An internally inconsistent run
    # stays status=ERROR and never sets it.
    #
    # NotRequired because it is genuinely absent on a normal run — every reader tests
    # for its presence rather than expecting a value. The type checker reports this
    # line as "NotRequired[] can be only used in a TypedDict definition": AgentState
    # *is* a TypedDict, but it ships without a py.typed marker, so the base resolves
    # to Any here and the qualifier cannot be recognised. That is the same
    # distributed-package gap behind the other findings in this package.
    error_code: NotRequired[str]

    # pre_process (parse + rubric load)
    document_body: str
    detected_language: str
    rubric_json: Optional[str]  # JSON dict — quality rubric (weights, thresholds)
    rubric_version: str

    # main (LLM dimensions)
    flagged_spans_json: Optional[str]  # JSON list[dict] — flagged spans across dimensions
    unsupported_claims: list[str]  # primitive list of strings — msgpack-safe as-is
    dimension_scores_json: Optional[str]  # JSON dict — per-dimension 0-100 scores
    remediation_items_json: Optional[str]  # JSON list[dict] — per-flag remediation suggestions

    # post_process (aggregate + report)
    quality_score: int
    verdict: str
    quality_report_json: Optional[str]  # JSON dict — final structured quality report
    validation_error: str
