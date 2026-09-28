"""AgentCore Platform v1.0 — CMN-C1-516 graph (Cat 1 Validate, flat 3-slot).

Enterprise AI-Generated Content Quality & Anti-Slop Validation Agent.
L1 Base: AgentBaseGraph (Level 1 direct inheritance).

Pipeline:
    START → initialize → pre_process(ParseRubric) → main(QualityValidation)
          → post_process(AggregateReport) → finalize → END
"""

from typing import Any

from framework.graph.agent_base_graph import AgentBaseGraph

from src.nodes.main_node import QualityValidationNode
from src.nodes.post_process_node import AggregateReportNode
from src.nodes.pre_process_node import ParseRubricNode
from src.schemas.state import State
from src.services.state_serde import from_json


class ContentQualityValidationAgent(AgentBaseGraph):
    """Cat 1 Validate agent — document quality + anti-slop validation."""

    @property
    def name(self) -> str:
        return "cmn-c1-516"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects initialize + finalize
        cfg = self.config if hasattr(self, "config") and self.config else {}
        self._nodes["pre_process"] = ParseRubricNode()
        self._nodes["main"] = QualityValidationNode(
            llm=cfg.get("llm"),
            retriever=cfg.get("retriever"),
            top_k=cfg.get("top_k", 5),
            max_remediation_words=cfg.get("max_remediation_words", 50),
        )
        self._nodes["post_process"] = AggregateReportNode()

    # add_edges() is NOT overridden — backbone wiring belongs to the framework.

    def get_output(self, state: dict[str, Any]) -> dict[str, Any]:
        """Expose the structured quality report to the caller.

        ADR-005: the report is checkpointed as a JSON string (quality_report_json);
        it is decoded back to a dict here, at the output boundary, so the caller
        receives the full structured report while State stays msgpack-safe.
        """
        base = super().get_output(state)
        base["output"] = from_json(state.get("quality_report_json"), None) or base.get("output")
        return base if isinstance(base, dict) else {}


# Stable alias for the standalone entry point import (src/api/server.py).
Graph = ContentQualityValidationAgent
