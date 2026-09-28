# CMN-C1-516 — Design Specification

Enterprise AI-Generated Content Quality & Anti-Slop Validation Agent.

## Position in AgentCore Architecture

- **Agent Class**: `ContentQualityValidationAgent`
- **L1 Base**: `AgentBaseGraph` (Level 1 direct inheritance; other templates are referenced as
  patterns only, never as inheritance targets).
- **Category**: Cat 1 (single technical capability — document quality validation, generic
  via a YAML rubric).
- **Three-Layer Separation**:
  - State: flat `TypedDict` extending `AgentState` (no Pydantic — msgpack incompatible).
  - Node: L1 inheritance (`FunctionNode.execute(self, state) -> dict` override only).
  - Graph: composition — flat 3-slot `AgentBaseGraph` backbone.

## Architecture (Cat 1, flat 3-slot)

```
START → initialize → pre_process(ParseRubric) → main(QualityValidation) → post_process(AggregateReport) → finalize → END
```

The 7 logical workflow steps map onto the fixed 3-slot Cat 1 backbone, with the
deterministic sub-steps factored into `src/services/`:

| Workflow step | Where | LLM? |
|---|---|---|
| 1. InputParse + RubricLoad | pre_process (ParseRubricNode) → parse_service, rubric_service | no |
| 2. SloppinessDetect | main → slop_service | yes (deterministic fallback) |
| 3. FactualConsistencyCheck | main → factual_service | yes + optional KB |
| 4. ToneAlignment + JapaneseProse | main → tone_service (keigo static rules + naturalness) | partial |
| 5. QualityAggregate | post_process → aggregate_service | no |
| 6. RemediationSuggest | main → remediation_service | yes (deterministic fallback) |
| 7. ReportGenerate + OutputValidate (S-3) | post_process → report_service | no |

## State Definition (agent-specific fields)

> **ADR-005:** composite payloads (rubric, flagged_spans, dimension_scores,
> remediation_items, quality_report) are NOT stored as `dict` / `list[dict]` in State — nested
> structures are not reliably msgpack-safe and risk silent checkpoint corruption. They are carried as
> JSON strings (`*_json: Optional[str]`) and (de)coded at the node boundary via
> `src/services/state_serde.py` (`to_json` / `from_json`). The caller still receives the full
> structured report: `graph.get_output()` decodes `quality_report_json` back to a dict at the output
> boundary (outside the checkpointed State), per the ADR-005 remediation pattern.

| Field | Type | Purpose |
|-------|------|---------|
| document_body | str | parsed document text |
| detected_language | str | ja / en |
| rubric_json / rubric_version | Optional[str] (JSON dict) / str | quality rubric + version stamp |
| flagged_spans_json | Optional[str] (JSON list[dict]) | flags across dimensions |
| unsupported_claims | list[str] | factual-check misses (primitive list — msgpack-safe) |
| dimension_scores_json | Optional[str] (JSON dict) | anti_slop / factual / tone / completeness (0-100) |
| remediation_items_json | Optional[str] (JSON list[dict]) | per-flag ≤50-word fix |
| quality_score / verdict | int / str | weighted score + PASS/CONDITIONAL/FAIL, or 0 / `NOT_EVALUATED` on a degraded run (§Rejection handling) |
| quality_report_json | Optional[str] (JSON dict) | structured report (PII-redacted + excerpt-truncated) |
| validation_error | str | downgrade signal |
| error_code | NotRequired[str] | degradation marker — absent on a normal run (§Rejection handling) |

**State constraints:** flat TypedDict of msgpack-safe primitives only; no `dict`/`list[dict]` composite
fields (ADR-005), no credentials/Pydantic/InvocationContext.

## Rejection handling — degraded vs failed

Nothing is ever silently passed through: a refused document produces no quality report.
How the refusal is *reported* depends on whether the caller can act on it.

| Refusal | Reported as |
|---|---|
| Empty or whitespace-only document | `status=SUCCESS`, `error_code=EMPTY_INPUT` |
| Document over the size cap | `status=SUCCESS`, `error_code=DOCUMENT_TOO_LARGE` |
| Body empty once markup is stripped (only code fences / heading markers) | `status=SUCCESS`, `error_code=NO_TEXT_CONTENT` |
| Internally inconsistent run — nothing to validate and no `error_code` set | `status=ERROR` |
| Framework security-gate refusal | `status=ERROR` |

The first group is the caller's to fix, and a non-SUCCESS result reaches them as a terminal
failure naming only the exception type — so the reason has to travel in the output. The second
is a defect rather than a caller mistake. The third stays a bare failure on purpose: naming the
pattern that tripped the gate would tell the sender how to get past it.

A degraded run validates nothing. `QualityValidationNode` skips all four dimensions and the
remediation pass; `AggregateReportNode` builds the report from the allow-listed code alone —
every field is a constant, so no value the rejected request had already put into State reaches
the caller. `quality_score` is `0` and `verdict` is `NOT_EVALUATED` (distinct from PASS /
CONDITIONAL / FAIL: no validation ran, as opposed to validation that ran and passed).
`formatted_output` and `result` carry the reason sentence. The report's `message` key is present
on every run and holds `""` on a normal one, so the key does not appear and disappear with the
outcome. Wording lives in `src/services/degradation.py` and is derived from the code alone — no
document text, no size, no line position. The audit events (`document_rejected` /
`validation_skipped` / `quality_report_degraded`) record the refusal.

## Security Model (5-layer)

- **S-1**: `required_trust_level: VERIFIED_EXTERNAL` declared on `ParseRubricNode` (code) and as the
  agent default (agent.yaml) — the S-1 trust gate denies ANONYMOUS callers before `execute()` runs.
  50KB document size cap in pre_process.
- **S-2**: framework input gate (PII pre-sanitization).
- **S-3 output discipline**: in `report_service.build_report`, every flagged/remediation
  excerpt is **PII-redacted** (email / phone / Japanese マイナンバー bounded-quantifier regex → `[REDACTED_*]`) **before**
  being deterministically truncated to ≤100 chars. Length truncation alone is not redaction — a 100-char
  excerpt can still leak a full email/phone, so redaction runs first. No full-passage reproduction.
- **S-3 Secret Isolation**: `bound_secrets()`/`secrets_factory()`/`provision_secrets()` at entry; no
  `os.environ`.
- **S-4**: `emit_trace_event()` in the main validation node.
- **S-5**: import-time credential scan; audit logs record document_hash/rubric_version/score, never raw content.

## Composition Pattern

- **Pattern**: flat Cat 1 (single base, no GraphNode/subgraph). Single-responsibility: one Validate capability.

## Import Isolation Confirmation

- No agenticstar-platform (Level 0) imports; only `framework/` + `shared/`.

## Design Decision Record

| Decision | Chosen | Rationale |
|----------|--------|-----------|
| L1 base type | AgentBaseGraph | Cat 1 fixed pipeline |
| Node/tool split | deterministic → services, LLM → main node | keeps graph at reasoning + gate layer |
| Rubric | YAML config (rubric-as-config) | industry-agnostic; next Validate template faster |
| S-3 | deterministic ≤100-char excerpt truncation | no full-passage reproduction |

## 1. Deployment entry points

The agent is reachable through two entry points, and both resolve their runtime inputs the same way.

| Entry point | File | Used by |
|---|---|---|
| Standalone HTTP | `src/api/server.py` | staging rehearsal, direct invocation |
| Marketplace one-shot Pod | `cli.py` | the platform runner (container `CMD`) |

Both read runtime parameters from `config/config.yaml` — the manifest carries discovery metadata
only — and both scope secrets to the same location (`namespace=cmn`, `agent_name=cmn-c1-516`), so a
secret provisioned for one path resolves identically on the other.

**Deployment-provided LLM client.** The three Azure OpenAI connection values
(`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT` — the bare resource endpoint — and
`AZURE_OPENAI_DEPLOYMENT`) are resolved through the agent's own secret provider, never from the
process environment. Both entry points build the client only when all three resolve and pass it in
as `config["llm"]`; when any is absent the key stays unset and the graph keeps its deterministic
path. The manifest declares the three secrets and the provider extra.

**Progress events.** Each pipeline stage emits a non-terminal progress event at its start, so a
caller sees the run advancing. Outside the Marketplace runtime the emitter resolves to a no-op, so
the same code is safe on every path. Terminal events belong to the platform runner and are never
emitted by this agent.

**Caller authentication at the standalone entry point.** A caller that no upstream middleware
vouched for stays anonymous unless it presents a deployment-level credential: the external bearer
token grants the verified-external level, and a separate staging-only runner credential is the only
way to reach the internal level. Trust established upstream is never changed.
