# Bifura — Architecture & Contract Reconciliation Report

**Date:** October 22, 2026  
**Context:** Bifura Hackathon Architecture Foundation  
**Scope:** Reconciled data contracts, model canonicalization, schema versioning, safety decision integration, taxonomy alignment, directory layout, and test verification.

---

## 1. Executive Summary

Following the initial repository inspection, all contradictions between the Master Specification (`BIFURA_MASTER_PROJECT_SPEC.md`), the Execution Plan (`BIFURA_EXECUTION_PLAN.md`), the API Contracts Document (`docs/API_AND_DATA_CONTRACTS.md`), and the Python implementation have been resolved.

A unified source of truth has been established under `src/bifura/schemas/models.py`. Backward compatibility is preserved across all imports via `src/bifura/contracts.py` and `src/bifura/__init__.py`. All 5 baseline tests plus 8 new reconciliation tests pass with a 100% success rate (13/13 passed).

---

## 2. Reconciled Areas

### 2.1 Model Module Location
* **Canonical Path:** `src/bifura/schemas/models.py` (`bifura.schemas.models`).
* **Compatibility Layer:** `src/bifura/contracts.py` and `src/bifura/__init__.py` re-export all canonical models and aliases. Teammates can import from either module transparently.
* **Cleanup:** Removed the empty artifact directory `src/bifura/contracts/`.

### 2.2 Model & Contract Names
Canonical names from the specification have been matched with execution plan aliases:
* `ToolCallProposal` (alias: `ToolProposal`)
* `SafetyDecisionRecord` (alias: `SafetyDecision` — prevents collision with the `DecisionType` enum)
* `DeviationRecord` (alias: `DeviationResult`)
* `VerificationReport` (aliases: `TestReport`, `ReplayReport`)
* `DependencyEdge` (edge contract) and `ImpactGraph` (graph container)

### 2.3 Mandatory Schema Versioning
* Added `schema_version: str = "1.0"` to base model `Contract(BaseModel)`.
* Every model inherits this field with a default value of `"1.0"`.
* Serializing produces `"schema_version": "1.0"`; deserializing incoming payloads containing `"schema_version"` succeeds without `extra="forbid"` errors.

### 2.4 TraceEvent Field Alignment
* Supports structured payloads (`input_data`, `output_data`, `state_delta`) for in-memory and UI graph processing.
* Preserves storage references (`input_ref`, `output_ref`, `state_before_ref`, `state_after_ref`) for file-backed data.
* Includes `actor`, `provenance`, `tool_call_id`, `depends_on_event_ids`, and `tool_name` so both doc specs and test code work seamlessly.

### 2.5 Safety Decision & Execution Auditing
* `SafetyDecisionRecord` records `decision` (`ALLOW`, `REVIEW`, `BLOCK`), `policy_rule` / `rule_ids`, `reason`, and `execution_status` (`not_started`, `blocked_before_execution`, `executed`, etc.).
* `ToolExecutionResult` captures post-execution data from the executor (`executed`, `success`, `result_data`, `error_type`).

### 2.6 Failure Category Taxonomy
Enforced the 7 canonical failure categories in `FailureCategory(str, Enum)`:
1. `tool_input_validation`
2. `state_or_dataflow`
3. `planning_or_tool_sequence`
4. `retry_logic`
5. `external_tool_or_environment`
6. `model_reasoning_or_instruction_handling`
7. `unknown_insufficient_evidence`

*(Includes aliases: `STATE_PROPAGATION -> state_or_dataflow`, `PLAN_TOOL_SEQUENCE -> planning_or_tool_sequence`, `UNKNOWN -> unknown_insufficient_evidence`).*

### 2.7 Standardized Data Directory Structure
Created and git-tracked the required directories:
* `data/fixtures/`: Deterministic scenario inputs and expected outcomes.
* `data/incidents/`: Seeded and recorded incident cases.
* `data/evaluation/`: Benchmark datasets and evaluation scripts.
* `data/datasets/`: Exported incident datasets for model training.
* `results/`: Test outputs, candidate diffs, and replay logs.
* `tests/unit/`: Unit tests.

---

## 3. Canonical Model Reference

| Canonical Model | Allowed Alias | Purpose |
| :--- | :--- | :--- |
| `RunRecord` | — | Single agent execution run |
| `TraceEvent` | — | Individual trace event in the execution timeline |
| `ToolCallProposal` | `ToolProposal` | Untrusted tool proposal from agent / LLM |
| `SafetyDecisionRecord` | `SafetyDecision` | Central policy engine authorization decision |
| `ToolExecutionResult` | — | Execution outcome from central tool executor |
| `DeviationRecord` | `DeviationResult` | First observed mismatch from invariant/expectation |
| `HypothesisRecord` | — | Evidence-backed root cause hypothesis |
| `IncidentRecord` | — | Historical case preserved as a learning asset |
| `IncidentMatch` | — | Retrieval match with explanation & similarity |
| `PredictionResult` | — | Classifier failure-category prediction |
| `DependencyEdge` | — | Granular causal/dataflow edge between events |
| `ImpactGraph` | — | Complete execution impact graph structure |
| `PatchRecord` | — | Candidate code/prompt fix in isolated sandbox worktree |
| `VerificationReport` | `TestReport`, `ReplayReport` | Unified test and replay verification record |

---

## 4. Files Modified and Created

* `src/bifura/schemas/models.py`: **[Created]** Canonical Pydantic v2 data models.
* `src/bifura/schemas/__init__.py`: **[Created]** Schema module exports.
* `src/bifura/contracts.py`: **[Updated]** Re-exports canonical models and aliases for backwards compatibility.
* `src/bifura/__init__.py`: **[Updated]** Top-level package exports.
* `tests/test_contracts.py`: **[Updated]** 13 comprehensive unit tests (5 baseline + 8 new).
* `docs/API_AND_DATA_CONTRACTS.md`: **[Updated]** Documented canonical module location and aliases.
* `data/fixtures/.gitkeep`, `data/datasets/.gitkeep`, `data/incidents/.gitkeep`, `data/evaluation/.gitkeep`, `results/.gitkeep`, `tests/unit/.gitkeep`: **[Created]** Tracked project directories.
* `src/bifura/contracts/`: **[Deleted]** Removed empty folder.

---

## 5. Verification & Test Results

* **Test Framework:** pytest 9.1.1 (Python 3.13.7)
* **Execution Command:** `.venv\Scripts\pytest -v`
* **Test Outcome:** **13 passed in 0.18s (100% Pass Rate)**

```text
tests/test_contracts.py::test_trace_event_accepts_valid_data PASSED
tests/test_contracts.py::test_trace_event_rejects_negative_sequence PASSED
tests/test_contracts.py::test_contract_rejects_unknown_fields PASSED
tests/test_contracts.py::test_tool_proposal_accepts_structured_arguments PASSED
tests/test_contracts.py::test_safety_decision_supports_block PASSED
tests/test_contracts.py::test_schema_version_defaults_and_serializes PASSED
tests/test_contracts.py::test_import_equivalence_between_schemas_and_contracts PASSED
tests/test_contracts.py::test_trace_event_supports_structured_data_and_references PASSED
tests/test_contracts.py::test_safety_decision_record_and_execution_status PASSED
tests/test_contracts.py::test_failure_category_canonical_taxonomy_and_aliases PASSED
tests/test_contracts.py::test_impact_graph_and_dependency_edge PASSED
tests/test_contracts.py::test_deviation_record_and_aliases PASSED
tests/test_contracts.py::test_verification_report PASSED
```
