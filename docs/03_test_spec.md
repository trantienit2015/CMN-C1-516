# CMN-C1-516 — Test Specification

## Test Strategy

- Test types: Unit (per node + services) + Integration (full graph) + Proof-of-Boundary.
- Each node ≥1 success + ≥1 error/edge; ≥1 full-graph compile+invoke.
- LLM/retriever injected as fakes; deterministic service baselines keep tests runnable.

## Framework Compliance Tests (TC)

| TC-ID | Test | Where | Expected |
|-------|------|-------|----------|
| TC-01 | State flat TypedDict; no Pydantic | tests/proof_of_boundary/test_state_safety.py | pass |
| TC-02 | Caller-correctable rejection (empty / oversize / markup-only document) → degraded success: `status=SUCCESS` + allow-listed `error_code`, no validation, `NOT_EVALUATED` report (§Rejection handling) | test_pre_process_node / test_security_boundaries / test_graph | SUCCESS + `error_code`, never a silent pass |
| TC-02b | Internally inconsistent run — nothing to validate with no `error_code` set — stays a failure | test_main_node.test_empty_body_errors | status ERROR + error_log |
| TC-03 | No credentials in source/state | gate-credential-scan + state_safety | pass |
| TC-04 | Secrets via provider pattern, not os.environ | src/api/server.py | pass |
| TC-05 | emit_trace_event for side-effecting node | QualityValidationNode | trace emitted |
| TC-06 | Node statelessness | code review | pass |
| TC-07 | No `_invoke_impl`; execute(self, state) | test_pre_process_node.test_execute_signature | pass |
| TC-08 | S-1 trust gate (VERIFIED_EXTERNAL) declared on ParseRubricNode (code) + agent.yaml | test_security_boundaries.TestPB004TrustGateAtS1 / agent.yaml | enforced |
| TC-09 | ADR-005 State serde round-trip (composite → JSON str) | test_services.test_state_serde_* | pass |
| TC-10 | S-3 PII redaction (email/phone/My Number) before excerpt truncation | test_services.test_redact_pii_* / test_post_process_node.test_pii_redacted_in_flagged_excerpt | PII masked |

## Proof-of-Boundary Tests (PB)

| PB-ID | Boundary | Where | Expected |
|-------|----------|-------|----------|
| PB-2 | State serialization (primitives only; no dict/list[dict] — ADR-005) | test_state_safety.py (test_state_file_safety + test_no_composite_dict_fields) | pass |
| PB-4 | Import isolation (no Level 0) | test_import_isolation.py | 0 violations |
| PB-6 | Full pipeline compile + invoke | tests/integration/test_graph.py | SUCCESS, ≥5 nodes |
| PB-001 | Injection / oversized excerpt bounded at S-3 report (+ PII redacted) | test_security_boundaries.TestPB001* | payload truncated; PII masked |
| PB-002 | Oversized document refused before parsing | test_security_boundaries.TestPB002OversizedAtS1 | degraded (`SUCCESS` + `DOCUMENT_TOO_LARGE`), no body parse, reason carries no document content |
| PB-003 | Empty/whitespace input degrades gracefully | test_security_boundaries.TestPB003EmptyInputGraceful | degraded (`SUCCESS` + `EMPTY_INPUT`), no crash |
| PB-004 | S-1 trust gate denies ANONYMOUS before execute() | test_security_boundaries.TestPB004TrustGateAtS1 | ANON denied, VERIFIED allowed |
| PB-SLOP-001 | Known AI-tell filler MUST be flagged | test_services.test_pb_slop_filler_flagged | generic_filler flagged |

## Node / Service Coverage

| Unit | Success | Error/edge |
|------|---------|-----------|
| ParseRubricNode | test_success_parse_and_rubric | test_empty_input_degrades / test_oversize_input_degrades / test_markup_only_document_degrades / test_degraded_result_carries_no_caller_content |
| QualityValidationNode | test_success_flags_slop / test_clean_document_few_flags / test_japanese_keigo_inconsistency_flagged | test_empty_body_errors（コード無しの内部不整合）/ test_degraded_run_skips_validation / test_degraded_run_never_reaches_the_dimensions |
| AggregateReportNode | test_pass_verdict / test_excerpt_truncated_to_100 / test_pii_redacted_in_flagged_excerpt / test_normal_report_carries_an_empty_message | test_fail_verdict / test_validation_error_downgrades_pass / test_degraded_output_keeps_the_contract_shape / test_degraded_output_ignores_state_leftovers / test_unknown_code_still_explains_itself |
| services | parse/rubric/aggregate/slop + state_serde + redact_pii (test_services.py) | PB-SLOP-001 / TestDegradation（コードごとの文面・未知コード・入力値を含まないこと） |

## Rejection handling — degraded vs failed

A refusal the caller can act on ends the run as **SUCCESS carrying an allow-listed `error_code`**,
with the reason in `formatted_output` / `result` and in the report's `message`. The refusal itself
is unchanged: nothing is validated, no report is produced, and the audit events
(`document_rejected` / `validation_skipped` / `quality_report_degraded`) record it.

The reason has to travel in the output because the Marketplace runner converts a non-SUCCESS
result into a terminal failure whose text names only the exception type — a caller who sent an
unusable document would otherwise learn nothing about what to change.

`status=ERROR` is kept for what the caller cannot act on: an internally inconsistent run (nothing
to validate with no `error_code` set) and a framework security-gate refusal.

| Case | `error_code` | Covered by |
|---|---|---|
| Empty / whitespace-only document | `EMPTY_INPUT` | unit/test_pre_process_node.py, proof_of_boundary/test_security_boundaries.py, integration/test_graph.py::test_empty_input_degrades_instead_of_failing |
| Over the size cap | `DOCUMENT_TOO_LARGE` | unit/test_pre_process_node.py, proof_of_boundary/test_security_boundaries.py |
| No text once markup is stripped | `NO_TEXT_CONTENT` | unit/test_pre_process_node.py, integration/test_graph.py::test_markup_only_document_degrades |
| Nothing to validate without a code | — (`status=ERROR`) | unit/test_main_node.py::test_empty_body_errors |

### Properties asserted about a degraded run

| Property | Covered by |
|---|---|
| The validation is not merely empty — it is never entered (the anti-slop pass raises if reached) | unit/test_main_node.py::test_degraded_run_never_reaches_the_dimensions |
| The report keeps the documented key set; `message` is present on every run (`""` when normal) | unit/test_post_process_node.py, integration/test_graph.py::test_success_path_carries_an_empty_message |
| No value left in State by the rejected request reaches the output | unit/test_post_process_node.py::test_degraded_output_ignores_state_leftovers, integration/test_graph.py::test_degraded_output_never_echoes_the_document |
| The wording is derived from the code alone — no document text, no size | unit/test_services.py::TestDegradation, unit/test_pre_process_node.py::test_degraded_result_carries_no_caller_content |
| An unknown code still explains itself rather than emitting an empty reason | unit/test_services.py::TestDegradation, unit/test_post_process_node.py::test_unknown_code_still_explains_itself |

## Execution Summary

- Local: 74 passed / 3 skipped (unit + services + integration + proof_of_boundary) on the deployed wheel; ruff clean. Skips are the PB-5 (checkpointing disabled) and PB-7 (HITL disabled) auto-waivers.
- CI: gate-* + run-tests on GitLab pipeline.

## 1. Deployment path tests

### TC-DEP-01 Marketplace entry point identity — `tests/unit/test_cli_entry_point.py`

| Case | Expected |
|---|---|
| Identity is concrete | `agent_name` / `namespace` are non-empty and not the runner default |
| Identity matches the HTTP entry point | the values equal what `src/api/server.py` passes to `secrets_factory`; where that entry point provisions no secrets, they equal the manifest `namespace` and the lower-cased template id |
| The runner call uses the constants | `run_agent_marketplace` is called with the module constants, not inline literals |

### TC-DEP-02 Standalone entry point boundary — `tests/proof_of_boundary/test_server_llm_injection.py`

| Case | Expected |
|---|---|
| Boots with no credential provisioned | the module imports and the app/agent objects are constructed |
| External bearer never reaches the internal level | resolves to the verified-external level |
| Staging runner credential reaches the internal level | resolves to the internal level |
| Wrong or missing bearer while auth is enabled | rejected with 401 |
