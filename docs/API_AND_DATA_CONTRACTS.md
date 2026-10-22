# Bifura — API and Data Contracts (v1)

**Status:** Initial team contract for the hackathon prototype  
**Purpose:** One shared agreement for Member 1 (agent/traces/safety), Member 2 (Streamlit/dashboard/impact graph), and Member 3 (incident data/prediction/evaluation).  
**Rule:** Do not invent different field names or duplicate schemas inside individual modules. Update this document and the Pydantic models together if a change is necessary.

## 1. Decisions locked for v1

- Language: Python.
- Orchestration: LangGraph, adapting an established ReAct pattern for a small local agent-under-test.
- UI: Streamlit.
- Schemas and validation: Pydantic v2.
- Tests: pytest.
- Local application records: SQLite.
- Exportable fixtures/datasets/traces: JSON or JSONL.
- Prediction baseline: scikit-learn, only if labelled data is suitable.
- Graph: NetworkX + Plotly.
- IDs: strings containing UUIDs (UUID4 recommended).
- Time: ISO-8601 UTC timestamps ending in `Z`.
- Field names: `snake_case` in Python and JSON.
- Schema version: every persisted top-level record includes `schema_version`, starting at `"1.0"`.
- Missing information: use `null`/omitted optional fields and an explicit status such as `unknown`; never fabricate values.
- Model output is untrusted input. Trusted authorization/provenance context must be produced by backend orchestration, not accepted from an LLM claim.

## 2. Canonical schema location and ownership

Create Pydantic models in `src/bifura/schemas/models.py` (`bifura.schemas.models`). To support all teammates, `src/bifura/contracts.py` and `src/bifura/__init__.py` re-export all canonical models along with backward-compatible aliases:
- `ToolCallProposal` (alias `ToolProposal`)
- `SafetyDecisionRecord` (alias `SafetyDecision`)
- `DeviationRecord` (alias `DeviationResult`)
- `VerificationReport` (aliases `TestReport`, `ReplayReport`)
- `DependencyEdge` & `ImpactGraph`

The dashboard, agent, database layer, and evaluation code must import from either `bifura.schemas.models` or `bifura.contracts`.

| Contract | Owner | Reviewers |
|---|---|---|
| `RunRecord`, `TraceEvent`, `DependencyEdge`, `DeviationRecord`, `ToolCallProposal` | Member 1 | Members 2 and 3 |
| `SafetyDecisionRecord` and execution status | Member 1 | Members 2 and 3 |
| `IncidentRecord`, `IncidentMatch`, `PredictionResult`, dataset metadata | Member 3 | Members 1 and 2 |
| Dashboard display needs and graph rendering | Member 2 | Members 1 and 3 |
| `HypothesisRecord`, `PatchRecord`, `VerificationReport` | Member 1 | Members 2 and 3 |

Member 2 identifies any missing display fields, but must not create a separate UI-only schema that conflicts with the Pydantic models. Member 3 links incidents to existing `run_id` and `event_id` values rather than inventing a second trace format.

## 3. Shared enums

Use these exact values initially. Extend only by updating this document and tests.

```python
RunStatus = "pending" | "running" | "succeeded" | "failed" | "blocked" | "needs_review"
EventType = "task_started" | "llm_request" | "llm_response" | "tool_proposed" | "safety_decision" | "tool_started" | "tool_completed" | "tool_blocked" | "state_updated" | "assertion_passed" | "assertion_failed" | "error" | "run_finished"
ActorType = "user" | "agent" | "llm" | "safety_engine" | "tool" | "evaluator" | "system"
SafetyDecision = "ALLOW" | "REVIEW" | "BLOCK"
ExecutionStatus = "not_started" | "awaiting_review" | "blocked_before_execution" | "approved_not_executed" | "executed" | "execution_failed" | "cancelled"
ProvenanceType = "user_task" | "system_policy" | "trusted_orchestrator" | "tool_output" | "web_or_file_content" | "model_generated" | "unknown"
FailureCategory = "tool_input_validation" | "state_or_dataflow" | "planning_or_tool_sequence" | "retry_logic" | "external_tool_or_environment" | "model_reasoning_or_instruction_handling" | "unknown_insufficient_evidence"
RootCauseStatus = "suspected" | "verified" | "unknown" | "rejected"
IncidentReviewStatus = "new" | "investigating" | "reviewed_verified" | "reviewed_unconfirmed" | "rejected"
TrainingEligibility = "eligible" | "ineligible" | "pending_review"
PatchStatus = "proposed" | "created_in_sandbox" | "tests_running" | "verified_in_sandbox" | "failed_verification" | "rejected" | "awaiting_human_review"
VerificationStatus = "not_run" | "passed" | "failed" | "inconclusive"
ScoreKind = "probability" | "decision_score" | "similarity_score" | "rank_score"
DependencyType = "consumes_output" | "reads_state" | "writes_state" | "control_flow" | "inferred_dependency"
EvidenceStatus = "observed" | "confirmed" | "inferred"
```

`ALLOW` means the safety policy permits an action; it does **not** prove that the action executed successfully. Always record `execution_status` separately.

## 4. `RunRecord` — one agent task execution

Required fields:

```json
{
  "schema_version": "1.0",
  "run_id": "UUID",
  "task_text": "Prepare a summary from the supplied local fixture",
  "expected_outcome": "A summary file is created inside the authorized workspace",
  "status": "failed",
  "started_at": "2026-10-22T10:00:00Z",
  "finished_at": "2026-10-22T10:00:02Z",
  "agent_name": "bifura_practice_agent",
  "agent_version": "0.1.0",
  "llm_provider": null,
  "llm_model": null,
  "is_fixture": true,
  "reference_run_id": null,
  "tags": ["controlled_fault"]
}
```

Rules:
- `run_id` is unique and is the join key used by trace events, incidents, predictions, hypotheses, patches, and evaluation results.
- `expected_outcome` must be a human-readable target; step-level expectations are stored as assertion events/records.
- `is_fixture=true` means a controlled demonstration/test run, not an uncontrolled real user run.
- `reference_run_id` optionally links a known-good run for comparison.
- `llm_provider` and `llm_model` are null when scripted fallback mode is used; do not pretend a model was called.

## 5. `TraceEvent` — one recorded execution event

Required fields:

```json
{
  "schema_version": "1.0",
  "event_id": "UUID",
  "run_id": "UUID",
  "sequence": 3,
  "timestamp": "2026-10-22T10:00:01Z",
  "event_type": "tool_proposed",
  "actor": "agent",
  "name": "inspect_test_file",
  "summary": "Agent proposed inspecting a fixture file",
  "tool_call_id": "UUID-or-null",
  "input_data": {"path": "fixtures/input.json"},
  "output_data": null,
  "state_delta": null,
  "status": "observed",
  "provenance": "model_generated",
  "depends_on_event_ids": ["prior-event-UUID"],
  "evidence_refs": [],
  "error": null
}
```

Field rules:
- `sequence` increases within a run, but sequence alone does not prove causality.
- `input_data`, `output_data` and `state_delta` are JSON-compatible objects and may be null if not applicable.
- `tool_call_id` connects proposal, safety decision, execution, and result events for one call.
- `depends_on_event_ids` should only contain dependencies supported by captured data flow or explicit state lineage. Do not fill it merely because an event occurred earlier.
- `provenance` records source/lineage, not authorization. Authorization is checked separately by the safety engine.
- Avoid storing secrets or unnecessary private data in traces.

## 6. `ToolCallProposal` — untrusted proposed tool action

```json
{
  "schema_version": "1.0",
  "tool_call_id": "UUID",
  "run_id": "UUID",
  "proposal_event_id": "UUID",
  "tool_name": "inspect_test_file",
  "arguments": {"path": "fixtures/input.json"},
  "model_generated_metadata": {"reason": "Need to inspect the input"},
  "trusted_context_id": "UUID-created-by-backend",
  "created_at": "2026-10-22T10:00:01Z"
}
```

Rules:
- `tool_name` and `arguments` from the LLM are proposals, not permission grants.
- Do not trust model-generated fields like `authorized=true`, `trusted=true`, or a claimed source.
- `trusted_context_id` resolves to server-side task identity, provenance, authorized workspace, and permissions. Do not let the LLM construct or alter this context.
- A proposed action is never sent directly to the tool handler.

## 7. `SafetyDecisionRecord` — mandatory enforcement audit

```json
{
  "schema_version": "1.0",
  "decision_id": "UUID",
  "run_id": "UUID",
  "tool_call_id": "UUID",
  "decision": "BLOCK",
  "policy_version": "1.0",
  "rule_ids": ["workspace_scope"],
  "reason": "Resolved target is outside the authorized workspace",
  "evidence_refs": ["event-UUID"],
  "validated_target": "outside.txt",
  "decided_at": "2026-10-22T10:00:01Z",
  "execution_status": "blocked_before_execution",
  "review_status": "not_required",
  "reviewed_by": null
}
```

Enforcement requirements:
- The deterministic policy engine is the authority for mandatory safety constraints; LLM advice cannot override it.
- `REVIEW` means not executed until approval and a fresh/relevant authorization check.
- `BLOCK` must set `execution_status="blocked_before_execution"`; the tool handler must never be called.
- `ALLOW` may initially have `execution_status="not_started"`; change it to `executed` or `execution_failed` only after the executor reports the outcome.
- Persist every decision and its reason/rule. Test prohibited tools, path traversal, out-of-workspace access, unauthorized writes, forged authorization claims, ambiguous actions, and any route that might bypass the guard.
- The safety engine is a mandatory feature, but it supports Bifura's larger autonomous debugging workflow rather than replacing it.

## 8. `DeviationRecord` — observed mismatch with expected behaviour

```json
{
  "schema_version": "1.0",
  "deviation_id": "UUID",
  "run_id": "UUID",
  "event_id": "UUID",
  "assertion_id": "expected-state-03",
  "expected": {"normalized_result": "valid"},
  "actual": {"normalized_result": null},
  "description": "The tool output did not satisfy the required schema",
  "first_observed_deviation": true,
  "evidence_refs": ["event-UUID"],
  "status": "observed"
}
```

Rules:
- A deviation is an observed mismatch. It is not automatically a verified root cause.
- “First deviation” means the earliest observed violation of a defined assertion/invariant, not necessarily the true internal cause.
- If the reference/expected behaviour is missing, record that limitation instead of guessing.

## 9. `HypothesisRecord` — candidate explanation

```json
{
  "schema_version": "1.0",
  "hypothesis_id": "UUID",
  "run_id": "UUID",
  "failure_category": "tool_input_validation",
  "statement": "The caller supplied an argument that did not match the tool schema",
  "supporting_evidence_refs": ["event-UUID", "test-UUID"],
  "contradicting_evidence_refs": [],
  "rank": 1,
  "score": null,
  "score_kind": null,
  "status": "suspected",
  "verification_notes": null
}
```

Rules:
- `rank` is relative ordering among hypotheses, not confidence.
- `score` stays null unless a component produces a meaningful score. Always specify `score_kind`; do not call a raw LLM score a calibrated probability.
- A hypothesis becomes `verified` only after investigation/test evidence supports it.

## 10. `IncidentRecord` — reviewed historical case

```json
{
  "schema_version": "1.0",
  "incident_id": "UUID",
  "source_run_id": "UUID",
  "observed_pattern": "Malformed tool result propagated to the next step",
  "failure_category": "state_or_dataflow",
  "first_deviation_event_id": "UUID",
  "root_cause_status": "verified",
  "root_cause_summary": "The result was stored without schema validation",
  "evidence_refs": ["event-UUID", "test-UUID"],
  "downstream_event_ids": ["event-UUID-2"],
  "verified_correction": "Validate the tool result before writing it to shared state",
  "regression_test_refs": ["test_state_validation"],
  "provenance": "controlled_fixture",
  "review_status": "reviewed_verified",
  "training_eligibility": "eligible",
  "dataset_version": "incidents-v1",
  "created_at": "2026-10-22T10:30:00Z",
  "reviewed_at": "2026-10-22T11:00:00Z"
}
```

Rules:
- `provenance` should identify at least `synthetic_fixture`, `controlled_fixture`, or `real_run` (use these values consistently in code).
- Keep the observed pattern, suspected root cause, verified root cause, and correction distinct.
- `training_eligibility="eligible"` is allowed only after an appropriate review confirms the label and evidence.
- An incident may be stored while unverified, but must not silently become a trusted supervised training label.
- Keep the original evidence and test references; do not only store a free-text lesson.

## 11. `IncidentMatch` — retrieval result

```json
{
  "schema_version": "1.0",
  "match_id": "UUID",
  "run_id": "UUID",
  "incident_id": "UUID",
  "method": "structured_similarity_v1",
  "similarity_score": 0.82,
  "score_kind": "similarity_score",
  "matched_features": ["failure_category", "tool_name", "argument_validation"],
  "why_relevant": "Both cases involve malformed arguments passed to the same tool category",
  "retrieved_at": "2026-10-22T10:30:00Z"
}
```

Rules:
- Similarity is not proof that the current execution has the same root cause.
- Always return the reason/features for a match.
- Retrieval can use a structured match before embedding search exists. Do not introduce embeddings just to satisfy the interface.

## 12. `PredictionResult` — likely failure category

```json
{
  "schema_version": "1.0",
  "prediction_id": "UUID",
  "run_id": "UUID",
  "model_version": "baseline-v1",
  "dataset_version": "dataset-v1",
  "prediction_mode": "trained_classifier",
  "candidates": [
    {"category": "tool_input_validation", "score": 0.71, "score_kind": "probability"},
    {"category": "state_or_dataflow", "score": 0.19, "score_kind": "probability"}
  ],
  "abstained": false,
  "abstention_reason": null,
  "supporting_incident_ids": ["UUID"],
  "created_at": "2026-10-22T10:31:00Z"
}
```

Rules:
- If the model is a calibrated probabilistic classifier, `score_kind` may be `probability`; otherwise use the correct score kind.
- `prediction_mode` must distinguish a real trained model from `rules_baseline` or `retrieval_only`.
- Include an `unknown_insufficient_evidence` option or abstain when evidence is inadequate.
- Prediction informs the investigation; it does not verify root cause, decide safety policy, or replace tests.
- Never hardcode illustrative score values in a live dashboard. The values above only demonstrate the field format.

## 13. `DependencyEdge` — impact graph relationship

```json
{
  "schema_version": "1.0",
  "edge_id": "UUID",
  "run_id": "UUID",
  "from_event_id": "UUID",
  "to_event_id": "UUID",
  "dependency_type": "consumes_output",
  "evidence_status": "confirmed",
  "evidence_refs": ["event-UUID"],
  "explanation": "The later tool call consumed the prior event's normalized output"
}
```

Rules:
- A graph edge represents dependency, not just chronological order.
- `confirmed` requires trace/data-flow or test evidence; `inferred` must be visually labelled as inferred.
- Do not present a speculative edge as proven causality.

## 14. `PatchRecord` and `VerificationReport`

Patch record fields:

```json
{
  "schema_version": "1.0",
  "patch_id": "UUID",
  "run_id": "UUID",
  "hypothesis_id": "UUID",
  "status": "created_in_sandbox",
  "workspace_ref": "disposable-worktree-id",
  "diff_path": "results/patches/patch-UUID.diff",
  "created_at": "2026-10-22T11:00:00Z",
  "requires_human_review": true
}
```

Verification report fields:

```json
{
  "schema_version": "1.0",
  "verification_id": "UUID",
  "run_id": "UUID",
  "patch_id": "UUID",
  "targeted_test_status": "passed",
  "regression_test_status": "passed",
  "replay_status": "passed",
  "baseline_run_id": "UUID",
  "corrected_run_id": "UUID",
  "summary": "The controlled failure is resolved and regression checks passed",
  "tested_at": "2026-10-22T11:15:00Z"
}
```

Rules:
- Use a disposable workspace/worktree. Do not patch production or merge automatically.
- A patch is not a verified fix until required tests and replay have actually run and passed.
- Preserve failed verification records; do not overwrite failures with a later success without retaining the history.

## 15. Relationships between records

- One `RunRecord` has many `TraceEvent` records.
- A `ToolCallProposal` has one or more related trace events and exactly one latest applicable safety decision for each execution attempt.
- A safety decision refers to a tool call and records whether execution occurred.
- A `DeviationRecord` points to the trace event and assertion that exposed the mismatch.
- A `HypothesisRecord` points to evidence refs and may be linked to an incident.
- An `IncidentRecord` points to its source run, first-deviation event, evidence, correction, and tests.
- A run can have several `IncidentMatch` records and one `PredictionResult` per model run/version.
- `DependencyEdge` links existing event IDs from the same run unless cross-run comparison is explicitly represented separately.
- A `PatchRecord` points to the hypothesis it aims to address; a `VerificationReport` points to the patch and baseline/corrected runs.

## 16. Storage choices

- Store runs, incidents, safety decisions, predictions, patches and verification reports in SQLite once persistence is implemented.
- Store raw trace events as JSONL for easy inspection/replay; SQLite indexing may be added without changing the Pydantic schema.
- Store deterministic scenario inputs and expected outcomes in `data/fixtures/`.
- Store versioned dataset exports in `data/datasets/`.
- Store actual evaluation outputs in `results/` with dataset and model versions.
- Store diffs and test/replay logs under `results/`; never commit secrets or API keys.
- Do not put the same mutable record in several competing files. SQLite is the application record store; JSON/JSONL are fixtures, exports, and replay artifacts.

## 17. What the dashboard must be able to display from these contracts

1. Run ID, task, expected outcome, final outcome, status, fixture/live label.
2. Timeline of trace events and detailed inputs, outputs, state changes, errors and dependencies.
3. First observed deviation and its assertion/evidence.
4. Ranked hypotheses with supporting and contradicting evidence and verification status.
5. Prediction categories, score meaning, model/dataset version and abstention status.
6. Retrieved incident matches, matching features and relevance explanation.
7. Impact graph with confirmed vs inferred edges.
8. Safety decision (`ALLOW`, `REVIEW`, `BLOCK`), rule IDs, reason and actual execution status.
9. Candidate patch diff and real targeted-test, regression-test and replay status.
10. Evaluation metrics linked to the exact dataset/model version.

The UI must distinguish fixtures from actual live runs and must not display example scores or results as measured results.

## 18. Minimum acceptance tests for the contracts

- Pydantic rejects a malformed record or invalid enum.
- Run and event IDs correctly connect trace, incident, prediction, safety decision and verification records.
- A tool proposal cannot self-authorize through model-generated fields.
- A prohibited action is logged with `BLOCK` and `blocked_before_execution`, and its tool handler is not invoked.
- A `REVIEW` action remains unexecuted before approval.
- `ALLOW` is distinct from successful execution.
- First-deviation records identify an assertion/event and do not automatically claim a verified root cause.
- Incident retrieval returns its match reason and never acts as proof of risk.
- Unverified incidents are ineligible as trusted supervised training labels.
- Prediction output identifies the model/dataset version and score semantics.
- A dependency edge marked `confirmed` has evidence references; inferred edges are labeled as inferred.
- Patch status cannot claim verified success before targeted tests, regression tests and replay have completed.

## 19. Thirty-minute schema agreement meeting

1. Member 1 creates the canonical Pydantic models for run, trace, tool proposal, safety decision, deviation, hypothesis, dependency edge, patch and verification.
2. Member 3 creates the incident, incident-match, prediction and dataset metadata models using the IDs and category values above.
3. Member 2 checks that these models provide everything needed for the first dashboard and lists missing display fields without inventing alternate schemas.
4. All three run a tiny serialization test and commit the schema contract.
5. After this checkpoint, any schema change must be discussed, documented here, and accompanied by updated tests.

## 20. Instructions for coding AIs

Read `BIFURA_MASTER_PROJECT_SPEC.md`, `BIFURA_EXECUTION_PLAN.md`, and this file before coding. Import and reuse the canonical Pydantic schemas. Do not invent competing field names, safety paths, status values, or data stores. Ask the team before changing a shared contract. Implement only the assigned module, run relevant tests, and report actual changed files, command output, test results, data limitations, and unresolved issues. Never fabricate a trace, safety decision, prediction result, causal relationship, model score, or verified fix.
