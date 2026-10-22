# Bifura — Shared Integration Contract (v1.0)

**Status:** Approved Shared Integration Contract  
**Authority:** Binds Member 1 (Agent & Execution), Member 2 (Safety Policy & Dashboard), and Member 3 (Incident Memory & Prediction)  
**Schema Authority:** `src/bifura/schemas/models.py` (canonical Pydantic v2 models)

---

## 1. Agreed File and Directory Ownership

To prevent merge conflicts and coordination overhead, each team member owns dedicated directories and modules. **No member may edit another member's owned files without explicit team agreement.**

```text
src/bifura/
├── agent/                  # MEMBER 1 — LangGraph/ReAct agent loop & planning
├── tracing/                # MEMBER 1 — Execution trace recording & normalization
├── analysis/               # MEMBER 1 — First-deviation detection & impact analysis
├── repair/                 # MEMBER 1 — Candidate patcher, test runner & replay
├── tools/
│   ├── policy.py           # MEMBER 2 — Deterministic safety policy evaluator (RETURNS decision)
│   └── executor.py         # MEMBER 1 — Central tool executor (CALLS & ENFORCES decision)
├── dashboard/              # MEMBER 2 — Streamlit reusable components & charts
└── learning/               # MEMBER 3 — Incident store, similarity retrieval, prediction & evaluation

app.py                      # MEMBER 2 — Streamlit dashboard entry point
data/
├── fixtures/               # MEMBER 2 — Mock run bundles & test fixtures
├── incidents/              # MEMBER 3 — Reviewed incident records & catalog
├── evaluation/             # MEMBER 3 — Benchmark test cases & held-out evaluation
├── datasets/               # MEMBER 3 — Exported incident datasets for model training
└── sandbox/
    └── runtime/            # MEMBER 1 — Writable runtime directory for patch sandbox (gitignored)
```

### Team Ownership Rules
* **Member 1 (Agent & Execution):** Owns `src/bifura/agent/`, `src/bifura/tracing/`, `src/bifura/analysis/`, `src/bifura/repair/`, and `src/bifura/tools/executor.py`. All tests created by Member 1 must be uniquely named (e.g., `tests/test_agent_*.py`, `tests/test_executor.py`).
* **Member 2 (Safety Policy & Dashboard):** Owns `src/bifura/tools/policy.py`, `app.py`, `src/bifura/dashboard/`, `data/fixtures/`, and uniquely named safety/dashboard tests (e.g., `tests/test_policy.py`, `tests/test_dashboard.py`).
* **Member 3 (Incident Memory, Prediction & Evaluation):** Owns `src/bifura/learning/` (implementing incident storage, similarity retrieval, classification, and evaluation inside this package), `data/incidents/`, `data/evaluation/`, `data/datasets/`, and uniquely named learning tests (e.g., `tests/test_learning.py`).
* **Tools Boundary:** `src/bifura/tools/policy.py` and `src/bifura/tools/executor.py` reside in the same package but have strict ownership. Member 2 writes the evaluator; Member 1 writes the executor. Neither may edit the other's file.
* **Parallel Workspaces:** Every member must work in a separate local clone on their own machine. Feature branches (`feature/agent-core`, `feature/safety-frontend`, `feature/incident-memory`) must remain independent.

---

## 2. Safety Evaluator Interface

### Function Signature
Member 2 implements the policy evaluator; Member 1 calls and enforces it:

```python
from bifura.schemas.models import ToolCallProposal, SafetyDecisionRecord

def evaluate_tool_action(
    proposal: ToolCallProposal,
    context: dict[str, Any]
) -> SafetyDecisionRecord:
    """Evaluate a proposed tool call against deterministic safety policies.
    
    Must return a valid SafetyDecisionRecord (ALLOW, REVIEW, or BLOCK).
    Does NOT execute any tools.
    """
    ...
```

### Required Context Keys Contract
The `context` dictionary passed to `evaluate_tool_action` must include these exact keys:

| Key | Type | Requirement | Description & Safe Default |
| :--- | :--- | :--- | :--- |
| `workspace_root` | `str` | **Required** | Absolute path to the controlled task workspace (`data/sandbox/`). Tools may only read within this boundary. |
| `sandbox_root` | `str` | **Required** | Absolute path to the writable runtime scratch area (`data/sandbox/runtime/`). Must be strictly contained within `workspace_root`. |
| `allowed_tools` | `list[str]` | **Required** | Whitelist of permitted tool names for this execution (e.g. `["read_file", "calculate"]`). |
| `permissions` | `dict[str, bool]` | **Required** | Permission flags mapping strings to booleans (see table below). |
| `provenance` | `str` | **Required** | Source identifier (`"trusted_orchestrator"`, `"agent"`, `"user_task"`). |
| `mode` | `str` | **Required** | Run mode: `"demo"`, `"investigation"`, `"replay"`, `"patch"`, or `"test"`. |

### Standard Permissions Dictionary
```python
permissions = {
    "allow_network": False,   # Default False. Network access is disabled.
    "write_sandbox": False,   # Default False. Writable only when run explicitly enables patch sandbox.
    "write_project": False,   # ALWAYS False. Modifying project source code or repo files is strictly prohibited.
}
```

---

## 3. Canonical Tool Argument Contracts & Path Security

### Standard Tool Shapes

1. **`read_file`**
   * Argument shape: `{"path": "fixtures/scenario_1.txt"}`
   * Scope: Path is relative to `workspace_root`.
   * Permitted operations: Read-only inspection of fixture and task files.
2. **`write_file`**
   * Argument shape: `{"path": "output.txt", "content": "..."}`
   * Scope: Path is relative to `sandbox_root`.
   * Policy Constraint: Allowed **only** if `permissions["write_sandbox"] is True` and `mode in ("patch", "test")`. Any write to `workspace_root` or repository files returns `DecisionType.BLOCK`.
3. **`calculate`**
   * Argument shape: `{"expression": "2 + 3"}`
   * Policy Constraint: Must evaluate using safe AST parsing or an explicit arithmetic operation allowlist. Using unrestricted `eval()` or `exec()` is strictly prohibited.

### Path Resolution and Containment Rules
* Path checks must resolve symlinks and normalize relative steps (`..`):
  ```python
  from pathlib import Path

  target = (Path(workspace_root) / path).resolve()
  # Robust component-aware containment check:
  try:
      target.relative_to(Path(workspace_root).resolve())
  except ValueError:
      # Path escaped workspace! Must BLOCK
      ...
  ```
* **Do not use string prefix checks** such as `str(target).startswith(str(root))`, as path manipulation (e.g. `/workspace_other`) can bypass naive string prefixes.
* Forbidden target names: Access to `.env`, `.git/`, SSH keys (`id_rsa`), `.venv/`, and parent traversal (`../`) outside the assigned boundary must immediately return `DecisionType.BLOCK`.

---

## 4. Safety Decisions and Execution Status

### Evaluator Responsibilities (Member 2)
* Evaluates the proposal against `allowed_tools`, path containment, and `permissions`.
* Returns a `SafetyDecisionRecord`:
  * `decision`: `SafetyDecisionType.ALLOW`, `SafetyDecisionType.REVIEW`, or `SafetyDecisionType.BLOCK`.
  * `policy_rule`: Name of the triggering policy rule (e.g. `"workspace_containment"`, `"unregistered_tool"`).
  * `reason`: Human-readable explanation for audit logging.
  * `execution_status`: Must be set to `ExecutionStatus.NOT_STARTED` (or `ExecutionStatus.BLOCKED_BEFORE_EXECUTION` if decision is `BLOCK`).
* **The evaluator never executes the tool.**

### Executor Responsibilities (Member 1)
* **Execution Gate:** The executor invokes the tool handler **only if** `decision.decision == SafetyDecisionType.ALLOW`.
* If `decision == SafetyDecisionType.BLOCK`: Tool is never called. Executor logs event `tool_blocked` with `execution_status = ExecutionStatus.BLOCKED_BEFORE_EXECUTION`.
* If `decision == SafetyDecisionType.REVIEW`: Tool is never called. Executor logs event `awaiting_review` with `execution_status = ExecutionStatus.AWAITING_REVIEW`.
* **Fail-Closed Rule:** If `evaluate_tool_action` raises an unhandled exception or returns an invalid object, the executor catches it, blocks execution, logs reason `"Safety evaluator exception: fail-closed"`, and records `ExecutionStatus.BLOCKED_BEFORE_EXECUTION`.
* The executor records successful execution outcomes in `ToolExecutionResult(executed=True, success=True/False, result_data=...)` and never modifies the evaluator's original decision.

---

## 5. Standard Trace Event Vocabulary & Ordering

All runtime events emitted by the agent and tools must use these exact lowercase `event_type` strings:

| Event Type | Emitted By | Description |
| :--- | :--- | :--- |
| `tool_proposed` | Agent / Orchestrator | Untrusted proposal containing tool name and proposed arguments |
| `safety_decision` | Safety Policy Engine | Result of policy evaluation (`ALLOW`, `REVIEW`, `BLOCK`) |
| `tool_started` | Central Executor | Tool invocation initiated (emitted only after `ALLOW`) |
| `tool_completed` | Central Executor | Tool completed execution successfully |
| `tool_failed` | Central Executor | Tool executed but raised an error or returned failure |
| `tool_blocked` | Central Executor | Tool blocked before execution by safety policy |
| `awaiting_review` | Central Executor | Tool suspended pending authorized human review |

### Logical Trace Sequence
1. `tool_proposed` (`actor="agent"`)
2. `safety_decision` (`actor="safety_engine"`)
3. Outcome branch:
   * Decision is `BLOCK` → `tool_blocked` (`actor="safety_engine"`)
   * Decision is `REVIEW` → `awaiting_review` (`actor="safety_engine"`)
   * Decision is `ALLOW` → `tool_started` (`actor="executor"`), followed by `tool_completed` or `tool_failed`

*(Note: Baseline contract tests referencing the historical string `"tool_call"` remain supported for backward compatibility; runtime code must emit the vocabulary above).*

---

## 6. Stable Demo Scenario Identifiers

The team will construct four reproducible scenarios:

1. **`success`**
   * *Behavior:* Agent reads a valid fixture file in `workspace_root`, computes a summary via `calculate`, and completes.
   * *Evidence:* All events succeed; zero deviations recorded (`DeviationRecord.found = False`).
   * *Run Status:* `succeeded`.
2. **`wrong_path`**
   * *Behavior:* Agent attempts `read_file` with path `../../secrets.txt`.
   * *Evidence:* Policy returns `BLOCK`. First deviation is recorded at the proposal event.
   * *Diagnosis:* `FailureCategory.TOOL_INPUT_VALIDATION`.
3. **`stale_state`**
   * *Behavior:* Tool executes successfully, but the agent updates intermediate state using an outdated variable.
   * *Evidence:* Output assertion fails on state verification event.
   * *Diagnosis:* `FailureCategory.STATE_OR_DATAFLOW`.
4. **`wrong_sequence`**
   * *Behavior:* Agent attempts `calculate` before `read_file` has populated the required operands.
   * *Evidence:* Precondition invariant check fails. (Tools and paths are otherwise valid).
   * *Diagnosis:* `FailureCategory.PLANNING_OR_TOOL_SEQUENCE`.

*Role Distinction:* `DeviationRecord` captures the observed invariant failure. Member 3's learning pipeline assigns the diagnosed `FailureCategory` to the resulting `IncidentRecord`.

---

## 7. Versioned Run-Bundle JSON Specification (v1.0)

Member 1 exports the run bundle upon task completion; Member 2 loads and renders it in the Streamlit UI:

```json
{
  "schema_version": "1.0",
  "scenario_id": "wrong_path",
  "run": {
    "schema_version": "1.0",
    "run_id": "run-001",
    "task_text": "Read summary from input fixture",
    "expected_outcome": "Valid summary generated without escaping workspace",
    "status": "blocked"
  },
  "expected_action_sequence": ["read_file", "calculate"],
  "actual_execution_summary": "Agent attempted path traversal and was blocked by safety policy.",
  "events": [
    {
      "schema_version": "1.0",
      "run_id": "run-001",
      "event_id": "ev-001",
      "sequence": 1,
      "event_type": "tool_proposed",
      "actor": "agent",
      "tool_name": "read_file",
      "input_data": {"path": "../../secrets.txt"}
    },
    {
      "schema_version": "1.0",
      "run_id": "run-001",
      "event_id": "ev-002",
      "sequence": 2,
      "event_type": "safety_decision",
      "actor": "safety_engine",
      "status": "blocked_before_execution"
    },
    {
      "schema_version": "1.0",
      "run_id": "run-001",
      "event_id": "ev-003",
      "sequence": 3,
      "event_type": "tool_blocked",
      "actor": "safety_engine",
      "status": "blocked_before_execution"
    }
  ],
  "safety_decisions": [
    {
      "schema_version": "1.0",
      "decision_id": "dec-001",
      "proposal_id": "prop-001",
      "decision": "BLOCK",
      "policy_rule": "workspace_containment",
      "reason": "Target path escapes authorized workspace root.",
      "execution_status": "blocked_before_execution"
    }
  ],
  "execution_results": [],
  "deviation": {
    "schema_version": "1.0",
    "run_id": "run-001",
    "found": true,
    "first_deviation_event_id": "ev-001",
    "expected_behavior": "Path strictly inside data/sandbox/",
    "observed_behavior": "Path ../../secrets.txt attempted",
    "description": "Path traversal attempt blocked by safety policy",
    "status": "observed"
  },
  "prediction": {
    "schema_version": "1.0",
    "run_id": "run-001",
    "predicted_categories": ["tool_input_validation"],
    "scores": {"tool_input_validation": 0.92},
    "score_meaning": "heuristic_support_score",
    "abstained": false
  },
  "incident_matches": [
    {
      "schema_version": "1.0",
      "incident_id": "inc-001",
      "similarity_score": 0.85,
      "match_reason": "Relative path traversal outside authorized workspace root."
    }
  ],
  "impact_graph": null,
  "verification": null
}
```

### Bundle Fields Specification
* `schema_version` (str, required): `"1.0"`.
* `scenario_id` (str, required): One of `"success"`, `"wrong_path"`, `"stale_state"`, `"wrong_sequence"`.
* `run` (RunRecord dict, required): Serialized `RunRecord.model_dump(mode="json")`.
* `expected_action_sequence` (list[str], required): Planned list of tool names.
* `actual_execution_summary` (str, required): Human-readable summary of the outcome.
* `events` (list[TraceEvent dict], required): Chronologically ordered trace events.
* `safety_decisions` (list[SafetyDecisionRecord dict], required): Recorded safety decisions.
* `execution_results` (list[ToolExecutionResult dict], required): Realized execution results.
* `deviation` (DeviationRecord dict, optional): `DeviationRecord.model_dump(mode="json")` or `null`.
* `prediction` (PredictionResult dict, optional): `PredictionResult.model_dump(mode="json")` or `null`. Score meaning must be labelled accurately (`"heuristic_support_score"`).
* `incident_matches` (list[IncidentMatch dict], optional): Retrieved similar incidents.
* `impact_graph` (ImpactGraph dict, optional): `ImpactGraph.model_dump(mode="json")` or `null`.
* `verification` (VerificationReport dict, optional): `VerificationReport.model_dump(mode="json")` or `null`.
