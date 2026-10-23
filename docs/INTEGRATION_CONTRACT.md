# Bifura — Shared Integration Contract (v1.0)

**Status:** Final Shared Integration Contract
**Authority:** Binds Member 1 (Agent & Execution), Member 2 (Safety Policy & Dashboard), and Member 3 (Incident Memory & Prediction)
**Schema Authority:** `src/bifura/schemas/models.py` (canonical Pydantic v2 models)
**Frozen Foundation:** No canonical schema models or frozen foundation files may be modified without explicit team agreement.

---

## 1. Agreed File Ownership and Frozen Foundation

To eliminate merge conflicts and coordination bottlenecks, each team member owns separate directories and modules:

```text
src/bifura/
├── agent/                  # MEMBER 1 — LangGraph/ReAct agent loop & planning
├── tracing/                # MEMBER 1 — Execution trace recording & normalization
├── analysis/               # MEMBER 1 — First-deviation detection & causal impact
├── repair/                 # MEMBER 1 — Candidate patcher, test runner & replay
├── tools/
│   ├── __init__.py         # FROZEN FOUNDATION — Package initialization
│   ├── policy.py           # MEMBER 2 — Deterministic safety policy evaluator (RETURNS decision)
│   └── executor.py         # MEMBER 1 — Central tool executor (ENFORCES decision & executes tools)
├── dashboard/              # MEMBER 2 — Streamlit reusable components & charts
└── learning/               # MEMBER 3 — Incident store, similarity retrieval, prediction & evaluation

app.py                      # MEMBER 2 — Streamlit dashboard entry point
data/
├── fixtures/               # MEMBER 2 — Tracked starter mock run bundles & test fixtures
├── runs/                   # RUNTIME ONLY — Output directory for real run bundles (gitignored)
├── incidents/              # MEMBER 3 — Reviewed historical incident catalog
├── evaluation/             # MEMBER 3 — Benchmark test cases & held-out evaluation
├── datasets/               # MEMBER 3 — Exported incident datasets for model training
└── sandbox/
    ├── fixtures/           # TRACKED — Controlled scenario input files
    └── runtime/            # RUNTIME ONLY — Writable scratch directory for patch sandbox (gitignored)
```

### Frozen Foundation Files
The following files are **frozen** and must remain unchanged during feature development:
1. `src/bifura/schemas/models.py`
2. `src/bifura/contracts.py`
3. `src/bifura/__init__.py`
4. `src/bifura/tools/__init__.py`
5. `tests/test_contracts.py`
6. `docs/API_AND_DATA_CONTRACTS.md`
7. `docs/INTEGRATION_CONTRACT.md`
8. `BIFURA_MASTER_PROJECT_SPEC.md`

*(Note: Teammates may create package `__init__.py` files inside their own module directories, e.g. `src/bifura/agent/__init__.py`, `src/bifura/learning/__init__.py`, `src/bifura/dashboard/__init__.py`).*

### Parallel Workspace Convention
* Every member must work in a separate local clone on their own machine.
* Dedicated feature branches:
  * Member 1: `feature/agent-core`
  * Member 2: `feature/safety-frontend`
  * Member 3: `feature/incident-memory`
* Teammates must never edit another member's owned files.

---

## 2. Policy Evaluator & Tool Executor Interface Distinction

The safety system cleanly separates policy evaluation from tool execution:

### A. Safety Policy Evaluator (Member 2 — `src/bifura/tools/policy.py`)
Pure deterministic evaluation function that judges a proposed action without executing it:

```python
from bifura.schemas.models import ToolCallProposal, SafetyDecisionRecord

def evaluate_tool_action(
    proposal: ToolCallProposal,
    context: dict[str, Any]
) -> SafetyDecisionRecord:
    """Evaluate a proposed tool action against deterministic safety policies.

    Must return a valid SafetyDecisionRecord (ALLOW, REVIEW, or BLOCK).
    Does NOT invoke any tool implementation.
    """
    ...
```

### B. Central Tool Executor (Member 1 — `src/bifura/tools/executor.py`)
Enforces the policy evaluator's decision and runs the tool only when permitted:

```python
from collections.abc import Callable
from typing import Any
from bifura.schemas.models import ToolCallProposal, SafetyDecisionRecord, ToolExecutionResult

def execute_tool_action(
    proposal: ToolCallProposal,
    context: dict[str, Any],
    evaluator: Callable[[ToolCallProposal, dict[str, Any]], SafetyDecisionRecord] | None = None
) -> tuple[SafetyDecisionRecord, ToolExecutionResult]:
    """Execute a proposed tool action only if the evaluator returns ALLOW.

    Enforces fail-closed safety semantics. Returns a tuple of:
    (SafetyDecisionRecord, ToolExecutionResult)
    using the existing canonical Pydantic models.
    """
    ...
```

### C. Fail-Closed Enforcement Rules
1. **Valid ALLOW Required:** The executor calls the tool handler **only if** `evaluator` returns a valid `SafetyDecisionRecord` with `decision == SafetyDecisionType.ALLOW`.
2. **Never Execute on BLOCK or REVIEW:** If `decision` is `BLOCK` or `REVIEW`, the tool handler is never called.
3. **Fail-Closed on Exceptions:** If `evaluator` is `None`, raises an unhandled exception, or returns an invalid object, the executor:
   - Does **not** execute the tool.
   - Generates a fail-closed `SafetyDecisionRecord` with `decision=SafetyDecisionType.BLOCK`, `policy_rule="fail_closed_guard"`, `reason="Evaluator missing, threw exception, or returned invalid decision."`, and `execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION`.
   - Generates a `ToolExecutionResult(proposal_id=proposal.proposal_id, decision_id=decision.decision_id, executed=False, success=False, error_type="SafetyBlockError", error_message="Execution blocked by safety policy or evaluator failure.")`.
4. **Immutability of Policy Decisions:** The executor never modifies or overwrites a valid policy decision returned by the evaluator.

### D. Standard Context Keys
The `context` dictionary passed to both evaluator and executor must contain:
* `workspace_root` (str, required): Absolute path to `data/sandbox/` (authorized task workspace).
* `sandbox_root` (str, required): Absolute path to `data/sandbox/runtime/` (writable patch scratch area).
* `allowed_tools` (list[str], required): Whitelist of permitted tools (e.g. `["read_file", "calculate", "write_file"]`).
* `permissions` (dict[str, bool], required):
  ```python
  permissions = {
      "allow_network": False,   # Network access is disabled by default.
      "write_sandbox": False,   # True only when candidate patching is active.
      "write_project": False,   # ALWAYS False. Modifying repo files is prohibited.
  }
  ```
* `provenance` (str, required): Origin identifier (`"trusted_orchestrator"`, `"agent"`, `"user_task"`).
* `mode` (str, required): One of `"demo"`, `"investigation"`, `"replay"`, `"patch"`, `"test"`.

---

## 3. Tool Argument Contracts, Containment & Calculator Limits

### A. `read_file`
* Argument shape: `{"path": "fixtures/scenario_1.txt"}`
* Path scope: Relative to `workspace_root`.
* Validation: Must resolve using `pathlib.Path(workspace_root, path).resolve()` and verify containment using `target.relative_to(Path(workspace_root).resolve())`.
* Forbidden targets: Any access resolving to `.env`, `.git/`, `.venv/`, SSH keys (`id_rsa`), or outside `workspace_root` returns `DecisionType.BLOCK`.

### B. `write_file`
* Argument shape: `{"path": "output.txt", "content": "..."}`
* Path scope: Relative to `sandbox_root`.
* Validation: Allowed **only** if `permissions["write_sandbox"] is True` and `mode in ("patch", "test")`. Target must resolve strictly inside `sandbox_root`. Any write to `workspace_root` or repository root returns `DecisionType.BLOCK`.

### C. `calculate`
* Argument shape: `{"expression": "15 * 4"}`
* **Consistent Calculator Limits (Applies to both Policy and Calculator):**
  * Maximum expression length: **200 characters**
  * Allowed operators: `+`, `-`, `*`, `/`, `//`, `%`, `**`, unary minus (`-`), and parentheses (`(`, `)`)
  * Maximum absolute numeric literal in expression: **`1e12`**
  * Maximum exponent magnitude: **`100`** (e.g. `x ** y` where `y <= 100`)
  * Maximum absolute intermediate/final result: **`1e12`**
  * Safe AST validation: Expression must be parsed using Python's `ast.parse(mode="eval")`. Only `ast.Expression`, `ast.BinOp`, `ast.UnaryOp`, `ast.Constant` (numbers), and allowed operator AST nodes are permitted.
  * Prevention of exponential blowup: Nested exponentiation such as `9**9**9` must be detected and rejected during AST inspection before calculation is attempted.
  * Prohibition: Unrestricted `eval()`, `exec()`, builtins, shell execution, or network calls are strictly forbidden.

---

## 4. Safety Decisions and Execution Status

Canonical `ExecutionStatus` values supported in `SafetyDecisionRecord` and `ToolExecutionResult`:
* `not_started`: Initial state before execution.
* `awaiting_review`: Suspended pending authorized human review (`REVIEW` decision).
* `blocked_before_execution`: Prevented from running by safety policy (`BLOCK` decision).
* `approved_not_executed`: Approved by reviewer but execution not yet attempted.
* `executed`: Successfully executed by central executor.
* `execution_failed`: Tool was invoked but raised a tool-level runtime error.
* `cancelled`: Execution cancelled by user or orchestrator.

---

## 5. Standard Trace Event Vocabulary and Ordering

All runtime events emitted by the agent, safety engine, and executor must use these exact lowercase `event_type` strings:
1. `tool_proposed` (`actor="agent"`): Proposed action submitted for evaluation.
2. `safety_decision` (`actor="safety_engine"`): Result of policy evaluation.
3. Outcome branch:
   * Decision is `BLOCK` → `tool_blocked` (`actor="safety_engine"`, `status="blocked_before_execution"`)
   * Decision is `REVIEW` → `awaiting_review` (`actor="safety_engine"`, `status="awaiting_review"`)
   * Decision is `ALLOW` → `tool_started` (`actor="executor"`), followed by `tool_completed` or `tool_failed`

*(Note: Baseline contract tests referencing `"tool_call"` remain supported; new runtime code must emit this standard vocabulary).*

---

## 6. Standardized Demo Scenario Definitions

All scenarios use consistent path conventions under `workspace_root` (`data/sandbox/`):

### 1. `success`
* **Input Fixture:** `fixtures/scenario_1.txt` containing valid arithmetic (e.g. `"15 * 4"`).
* **Expected Action Sequence:** `["read_file", "calculate", "write_file"]`.
* **Actual Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → `ALLOW`, returns `"15 * 4"`.
  2. `calculate(expression="15 * 4")` → `ALLOW`, returns `60.0`.
  3. `write_file(path="result.txt", content="60.0")` → `ALLOW` (inside `sandbox_root`), writes result.
* **Outcome:** `RunRecord(status="succeeded")`, `DeviationRecord(found=False)`.

### 2. `wrong_path`
* **Expected Action Sequence:** `["read_file", "calculate", "write_file"]`.
* **Actual Execution Sequence:**
  1. `read_file(path="../../secrets.txt")` proposed.
  2. Evaluator detects relative path traversal escaping `workspace_root` and returns `BLOCK`.
  3. Executor emits `tool_blocked`. Zero filesystem reads occurred.
* **Outcome:** `RunRecord(status="blocked")`.
* **Deviation:** `DeviationRecord(found=True, first_deviation_event_id="ev-001", description="Path traversal attempt blocked by safety policy")`.
* **Diagnosed Incident:** Member 3 assigns `FailureCategory.TOOL_INPUT_VALIDATION`.

### 3. `stale_state`
* **Context:** The agent reads fresh input from `fixtures/scenario_1.txt` (`"15 * 4"`), but the harness simulates an internal state failure where the agent references a stale cached variable (e.g. `"2 + 3"` from a prior step). Repository fixtures on disk are not mutated.
* **Expected Action Sequence:** `["read_file", "calculate", "write_file"]` with operand `60.0`.
* **Actual Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → `ALLOW`, reads `"15 * 4"`.
  2. `calculate(expression="2 + 3")` proposed with stale state value → `ALLOW` (valid arithmetic).
  3. Result is `5.0` instead of `60.0`.
  4. `write_file(path="result.txt", content="5.0")` writes wrong result.
* **Deviation:** Assertion check on calculation input detects mismatch between expected expression (`"15 * 4"`) and actual expression (`"2 + 3"`).
* **Diagnosed Incident:** Member 3 assigns `FailureCategory.STATE_OR_DATAFLOW`.

### 4. `wrong_sequence`
* **Context:** Out-of-order execution where an otherwise permitted write is attempted before calculating the result.
* **Expected Action Sequence:** `["read_file", "calculate", "write_file"]`.
* **Actual Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → `ALLOW`, reads `"15 * 4"`.
  2. `write_file(path="result.txt", content="uncomputed")` proposed before `calculate` has been called.
  3. With `write_sandbox` enabled, safety policy allows the write (`ALLOW`), but the workflow invariant precondition fails.
* **Deviation:** First deviation is recorded on the out-of-order `write_file` event because prerequisite calculation has not occurred.
* **Diagnosed Incident:** Member 3 assigns `FailureCategory.PLANNING_OR_TOOL_SEQUENCE`.

---

## 7. Versioned Run-Bundle Contract & Storage Locations

### Storage Locations
* **Tracked Starter Fixtures:** `data/fixtures/{scenario_id}.json` (committed to Git for dashboard testing).
* **Real Runtime Run Bundles:** `data/runs/{run_id}.json` (emitted by Member 1's agent; **gitignored** and must never be committed to Git).
* **Dashboard Discovery:** Member 2's Streamlit dashboard scans and loads run bundles from **both** `data/fixtures/` and `data/runs/`.

### Bundle Structure Specification (v1.0)
```json
{
  "schema_version": "1.0",
  "scenario_id": "wrong_path",
  "run": { ... },                     // Serialized RunRecord.model_dump(mode="json")
  "expected_action_sequence": ["read_file", "calculate", "write_file"],
  "actual_execution_summary": "Agent attempted path traversal on read_file and was blocked before execution.",
  "events": [ ... ],                  // Ordered list of serialized TraceEvents
  "safety_decisions": [ ... ],        // Serialized SafetyDecisionRecords
  "execution_results": [ ... ],       // Serialized ToolExecutionResults
  "deviation": { ... },               // Serialized DeviationRecord or null
  "prediction": { ... },              // Serialized PredictionResult or null
  "incident_matches": [ ... ],        // List of IncidentMatches wrapping IncidentRecord
  "impact_graph": { ... },            // Serialized ImpactGraph or null
  "verification": null                // Serialized VerificationReport or null
}
```

### Score Semantics Rule
In `prediction`, heuristic retrieval scores must be explicitly labelled:
`"score_meaning": "heuristic_support_score"`.
Heuristic scores must **never** be represented as calibrated probabilities.

---

## 8. Deterministic Testing and Provider Injection

To ensure tests are completely reproducible without flaky clocks or randomized UUIDs:
1. **Clock Injection:** Functions creating timestamps must accept an optional `clock` parameter:
   `clock: Callable[[], datetime] = utc_now`
2. **ID Generator Injection:** Functions generating IDs must accept an optional `id_generator` parameter:
   `id_generator: Callable[[], str] = lambda: str(uuid.uuid4())`
3. **Safety Evaluator Determinism:** The policy evaluator must be pure and deterministic. In tests, fixed IDs and clocks can be passed to verify exact record contents.
4. **No Shared `conftest.py`:** To prevent cross-branch merge conflicts, **do not create a shared `tests/conftest.py`**. Each test file (`tests/test_*.py`) must define its own local fixtures and test helpers.
