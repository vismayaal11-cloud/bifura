# Bifura — Shared Integration Contract (v1.1)

**Status:** Final Shared Integration Contract (Amendment v1.1)
**Authority:** Binds Member 1 (Agent & Execution), Member 2 (Safety Policy & Dashboard), Member 3 (Incident Memory & Prediction), and Integration Owner
**Schema Authority:** `src/bifura/schemas/models.py` (canonical Pydantic v2 models) & `src/bifura/schemas/bundle.py` (`RunBundle`)
**Frozen Foundation:** No canonical schema models or frozen foundation files may be modified without explicit team agreement.

---

## 1. Agreed File Ownership and Foundation

To eliminate merge conflicts and coordination bottlenecks, each team member owns separate directories and modules:

```text
src/bifura/
├── agent/                  # MEMBER 1 — LangGraph/ReAct agent loop & planning
├── tracing/                # MEMBER 1 — Execution trace recording & normalization
├── analysis/               # MEMBER 1 — First-deviation detection & causal impact
├── repair/                 # MEMBER 1 — Candidate patcher, test runner & replay (stretch goal)
├── tools/
│   ├── __init__.py         # FROZEN FOUNDATION — Package initialization
│   ├── policy.py           # MEMBER 2 — Deterministic safety policy evaluator (RETURNS decision)
│   ├── executor.py         # MEMBER 1 — Central tool executor (ENFORCES decision & executes tools)
│   └── local_tools.py      # MEMBER 1 — Local tool handlers (read_file, calculate, write_file)
├── dashboard/              # MEMBER 2 — Streamlit reusable components & charts
└── learning/               # MEMBER 3 — Incident store, similarity retrieval, prediction & evaluation

app.py                      # MEMBER 2 — Streamlit dashboard entry point
scripts/                    # INTEGRATION OWNER — Integration pipelines & release tooling
data/
├── fixtures/               # MEMBER 2 — Tracked starter mock run bundles & test fixtures
├── runs/                   # RUNTIME ONLY — Output directory for real run bundles (gitignored)
├── incidents/              # MEMBER 3 — Reviewed historical incident catalog
├── evaluation/             # MEMBER 3 — Benchmark test cases & held-out evaluation
├── datasets/               # MEMBER 3 — Exported incident datasets for model training
└── sandbox/
    ├── fixtures/           # MEMBER 1 — Tracked controlled scenario input files
    └── runtime/            # RUNTIME ONLY — Writable scratch directory for patch sandbox (gitignored)

tests/
├── fixtures/               # SHARED READ-ONLY — Shared fixture tables (calculator_cases.json)
├── test_agent_*.py         # MEMBER 1 — Agent and execution tests
├── test_policy.py          # MEMBER 2 — Safety policy evaluator tests
├── test_dashboard.py       # MEMBER 2 — Dashboard UI tests
├── test_learning.py        # MEMBER 3 — Incident memory and prediction tests
└── test_integration_*.py   # INTEGRATION OWNER — Integration bundle & pipeline tests
```

### Exact Ownership Matrix
* **MEMBER 1 — AGENT AND EXECUTION:**
  * `src/bifura/agent/`
  * `src/bifura/tracing/`
  * `src/bifura/analysis/`
  * `src/bifura/repair/`
  * `src/bifura/tools/executor.py`
  * `src/bifura/tools/local_tools.py`
  * `tests/test_agent_*.py`
  * `data/sandbox/fixtures/`
  *(Member 1 owns every implementation file in `src/bifura/tools/` except `policy.py`).*
* **MEMBER 2 — SAFETY POLICY AND DASHBOARD:**
  * `src/bifura/tools/policy.py`
  * `app.py`
  * `src/bifura/dashboard/`
  * `data/fixtures/`
  * `tests/test_policy.py`
  * `tests/test_dashboard.py`
* **MEMBER 3 — INCIDENT MEMORY AND PREDICTION:**
  * `src/bifura/learning/`
  * `data/incidents/`
  * `data/evaluation/`
  * `data/datasets/`
  * `tests/test_learning.py`
* **INTEGRATION OWNER — FINAL CONNECTION:**
  * `scripts/`
  * `tests/test_integration_*.py`
  * `docs/DEMO_RUNBOOK.md`

### Core Responsibility & Scoping Rules
1. **Strict File Separation:** No two owners may edit the same implementation files.
2. **Deviation vs. Diagnosis:**
   * Member 1 identifies observed deviations (`DeviationRecord` in `src/bifura/analysis/`).
   * Member 3 diagnoses failure categories (`FailureCategory` on `IncidentRecord` or `PredictionResult`) using the entire run bundle (trace events, tool/action data, expected-vs-actual evidence, and scenario context).
   * **Do NOT add `failure_category` to `DeviationRecord`.**
3. **Repair Scope (MVP vs Stretch):**
   * The repair module (`src/bifura/repair/`) is a stretch goal for one bounded correction and replay.
   * Member 1 is **not** required to build a general-purpose patcher or test-runner framework before the core MVP is operational.

### Frozen Foundation Files
The following files are **frozen** and must remain unchanged during feature development:
1. `src/bifura/schemas/models.py`
2. `src/bifura/schemas/__init__.py`
3. `src/bifura/contracts.py`
4. `src/bifura/__init__.py`
5. `src/bifura/tools/__init__.py`
6. `tests/test_contracts.py`
7. `docs/API_AND_DATA_CONTRACTS.md`
8. `BIFURA_MASTER_PROJECT_SPEC.md`
9. `tests/fixtures/calculator_cases.json` *(shared read-only table)*

---

## 2. Policy Evaluator & Tool Executor Interface Distinction

The safety architecture strictly separates pure policy evaluation from execution and enforcement:

### A. Safety Policy Evaluator (Member 2 — `src/bifura/tools/policy.py`)
Pure deterministic evaluation function that evaluates a proposed action against safety rules without invoking tools:

```python
from typing import Any
from bifura.schemas.models import ToolCallProposal, SafetyDecisionRecord

def evaluate_tool_action(
    proposal: ToolCallProposal,
    context: dict[str, Any]
) -> SafetyDecisionRecord:
    """Evaluate a proposed tool action against deterministic safety policies.

    Must return a valid SafetyDecisionRecord (ALLOW, REVIEW, or BLOCK).
    Does NOT invoke any tool implementation.
    Records the pre-execution status (e.g. BLOCKED_BEFORE_EXECUTION or NOT_STARTED).
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
3. **Fail-Closed on Exceptions or Missing Evaluator:** If `evaluator` is `None`, raises an unhandled exception, or returns an invalid object, the executor:
   - Does **not** execute the tool.
   - Generates a fail-closed `SafetyDecisionRecord` with `decision=SafetyDecisionType.BLOCK`, `policy_rule="fail_closed_guard"`, `reason="Evaluator missing, threw exception, or returned invalid decision."`, and `execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION`.
   - Generates a `ToolExecutionResult(proposal_id=proposal.proposal_id, decision_id=decision.decision_id, executed=False, success=False, error_type="SafetyBlockError", error_message="Execution blocked by safety policy or evaluator failure.")`.
4. **Immutability of Policy Decisions:** The policy evaluator returns the original decision. The executor **never edits or rewrites** that decision after execution. Tool execution outcomes are separately recorded in `ToolExecutionResult`.

### D. Standardized Context Keys and Scenario Context Table
The `context` dictionary passed to both evaluator and executor must contain all required keys:
* `workspace_root` (str, required): Absolute path to `data/sandbox/` (authorized task workspace).
* `sandbox_root` (str, required): Absolute path to `data/sandbox/runtime/` (writable patch scratch area).
* `allowed_tools` (list[str], required): Permitted tool names (e.g. `["read_file", "calculate", "write_file"]`).
* `permissions` (dict[str, bool], required):
  * `allow_network` (bool): Prohibited by default (`False`).
  * `write_sandbox` (bool): Default is `False`. Set to `True` when sandbox write permission is explicitly authorized.
  * `write_project` (bool): ALWAYS `False`. Prohibits writing to repository code, configuration, or tracked fixtures.
* `provenance` (str, required): `"trusted_orchestrator"`, `"agent"`, or `"user_task"`.
* `mode` (str, required): `"demo"`, `"investigation"`, `"replay"`, `"patch"`, or `"test"`.

#### Explicit Context Table for Demo Scenarios
No scenario may depend on unspecified defaults. All scenarios use the following exact context values:

| Scenario ID | `mode` | `allowed_tools` | `permissions["write_sandbox"]` | `permissions["allow_network"]` | `permissions["write_project"]` | `workspace_root` | `sandbox_root` |
|---|---|---|---|---|---|---|---|
| `success` | `"demo"` | `["read_file", "calculate", "write_file"]` | `True` | `False` | `False` | `data/sandbox/` | `data/sandbox/runtime/` |
| `wrong_path` | `"demo"` | `["read_file", "calculate", "write_file"]` | `False` | `False` | `False` | `data/sandbox/` | `data/sandbox/runtime/` |
| `stale_state` | `"demo"` | `["read_file", "calculate", "write_file"]` | `True` | `False` | `False` | `data/sandbox/` | `data/sandbox/runtime/` |
| `wrong_sequence` | `"demo"` | `["read_file", "calculate", "write_file"]` | `True` | `False` | `False` | `data/sandbox/` | `data/sandbox/runtime/` |

---

## 3. Tool Argument Contracts, Containment & Calculator Limits

### A. `read_file`
* Argument shape: `{"path": "fixtures/scenario_1.txt"}`
* Path scope: Relative to `workspace_root`.
* Validation: Target must resolve inside `workspace_root` using `pathlib.Path(workspace_root, path).resolve()`. Verified with `target.relative_to(Path(workspace_root).resolve())`.
* Forbidden targets: Any access resolving outside `workspace_root` or targeting `.env`, `.git/`, `.venv/`, SSH keys (`id_rsa`) returns `SafetyDecisionType.BLOCK`.

### B. `write_file` and Success-Scenario Permission Rule
* Argument shape: `{"path": "result.txt", "content": "60.0"}`
* Path scope: Relative to `sandbox_root`.
* **Standardized Permission Rule:** A `write_file` operation is eligible for `ALLOW` **only when**:
  1. The target resolves strictly inside `sandbox_root` (`data/sandbox/runtime/`).
  2. `permissions["write_sandbox"]` is explicitly `True`.
  3. The tool and arguments are valid.
  4. All other applicable safety requirements pass.
* **Mode Decoupling:** Do **not** require `mode` to be `patch` or `test` when sandbox writes have been explicitly authorized. A `demo` scenario with `write_sandbox=True` must be able to write its output to `sandbox_root`.
* **Strict Containment:** The default permission remains `False`. Never allow a write outside `sandbox_root`. The permission does not authorize arbitrary workspace or repository writes. Any write to `workspace_root` or repository root returns `SafetyDecisionType.BLOCK`.

### C. `calculate` Rules & Limits
* Argument shape: `{"expression": "15 * 4"}`
* **Standardized Calculator Limits (Shared by Policy and Local Calculator):**
  * Maximum expression length: **200 characters**.
  * Allowed operators: `+`, `-`, `*`, `/`, `//`, `%`, `**`, unary minus (`-`), and parentheses (`(`, `)`).
  * Maximum absolute numeric literal: **`1e12`**.
  * Maximum exponent magnitude: **`100`** (evaluated magnitude `abs(exponent) <= 100`).
  * Maximum absolute intermediate/final result: **`1e12`**.
* **Restricted AST Parsing Rules:**
  * Expressions must be parsed using Python's `ast.parse(mode="eval")`.
  * Only `ast.Expression`, `ast.BinOp`, `ast.UnaryOp`, `ast.Constant` (numbers), and allowed operator AST nodes are permitted.
  * **Reject Booleans & Complex Numbers:** Booleans (`True`, `False`) and complex numbers (`1+2j`, `3j`) are strictly forbidden as operands or results.
  * **Safe Exponent Validation:** Exponent values must be validated after safely evaluating their bounded subexpressions (e.g. `2 ** (3 + 2)` evaluates `5 <= 100`), not merely by checking whether the exponent AST node is a literal.
  * **Nested Exponentiation Protection:** Excessive nested exponent chains such as `9 ** 9 ** 9` must be detected and rejected during AST inspection before calculation is attempted.
  * **Result Boundaries:** Reject non-finite (`inf`, `-inf`, `nan`) or out-of-range (> `1e12`) results.
  * **Prohibitions:** Unrestricted `eval()`, `exec()`, builtins, shell execution, or network access are strictly forbidden.
* **Shared Test Cases Table:**
  * Member 1 and Member 2 must both validate against the shared test table at [`tests/fixtures/calculator_cases.json`](file:///c:/Users/Vismaya%20AL/OneDrive/Desktop/New%20folder/bifura/tests/fixtures/calculator_cases.json).
  * Neither member may edit this shared table independently.

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

The safety policy records the pre-execution status; the executor's `ToolExecutionResult` separately reports whether the tool ran (`executed: bool`) and whether it succeeded (`success: bool | None`).

---

## 5. Standard Trace Event Vocabulary and Actors

All runtime events emitted by the agent, safety engine, and tools must use canonical `EventType` and `ActorType` values from `src/bifura/schemas/models.py`:

| Event Type String | Canonical Enum | Standard Actor | When Emitted |
|---|---|---|---|
| `tool_proposed` | `EventType.TOOL_PROPOSED` | `"agent"` | Proposed action submitted for safety evaluation |
| `safety_decision` | `EventType.SAFETY_DECISION` | `"safety_engine"` | Safety policy evaluation completed |
| `tool_blocked` | `EventType.TOOL_BLOCKED` | `"safety_engine"` | Policy returned `BLOCK`; action blocked before execution |
| `tool_started` | `EventType.TOOL_STARTED` | `"tool"` | Policy returned `ALLOW`; tool invocation initiated |
| `tool_completed` | `EventType.TOOL_COMPLETED` | `"tool"` | Tool execution completed successfully |
| `error` | `EventType.ERROR` | `"tool"` | Tool execution failed with runtime error |
| `awaiting_review` | `ExecutionStatus.AWAITING_REVIEW` | `"safety_engine"` | Policy returned `REVIEW`; awaiting human review |
| `assertion_failed` | `EventType.ASSERTION_FAILED` | `"evaluator"` | Invariant violation (e.g. stale state mismatch or wrong sequence) |
| `assertion_passed` | `EventType.ASSERTION_PASSED` | `"evaluator"` | Invariant check passed |
| `state_updated` | `EventType.STATE_UPDATED` | `"agent"` | Agent state delta recorded |
| `task_started` | `EventType.TASK_STARTED` | `"agent"` | Agent run initiated |
| `run_finished` | `EventType.RUN_FINISHED` | `"agent"` | Agent run terminated |

*Note: The declared tool actor value is `"tool"`, not `"executor"`. Failed tool executions use `error`, and invariant checks use `assertion_failed`.*

---

## 6. Standardized Demo Scenario Definitions

All scenarios use consistent path conventions under `workspace_root` (`data/sandbox/`):

### 1. `success`
* **Input Fixture:** `fixtures/scenario_1.txt` containing valid arithmetic (`"15 * 4"`).
* **Expected Action Sequence:** `["read_file", "calculate", "write_file"]`.
* **Actual Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → `ALLOW`, reads `"15 * 4"`.
  2. `calculate(expression="15 * 4")` → `ALLOW`, calculates `60.0`.
  3. `write_file(path="result.txt", content="60.0")` → `ALLOW` (inside `sandbox_root`, `write_sandbox=True`), writes output.
* **Outcome:** `RunRecord(status="succeeded")`, `DeviationRecord(found=False)`.

### 2. `wrong_path`
* **Context:** Agent attempts to read a sensitive file outside the workspace.
* **Expected Action Sequence:** `["read_file", "calculate", "write_file"]`.
* **Actual Execution Sequence:**
  1. `read_file(path="../../secrets.txt")` proposed.
  2. Evaluator detects relative path traversal escaping `workspace_root` and returns `BLOCK`.
  3. Executor emits `tool_blocked`. Zero filesystem reads occurred.
* **Outcome:** `RunRecord(status="blocked")`.
* **Deviation:** `DeviationRecord(found=True, first_deviation_event_id="ev-001", description="Path traversal attempt blocked by safety policy")`.
* **Diagnosed Incident:** Member 3 assigns `FailureCategory.TOOL_INPUT_VALIDATION`.

### 3. `stale_state`
* **Context:** Deterministic in-memory simulated state update in the run harness. The agent references a stale cached value (`"2 + 3"`) instead of the freshly read content (`"15 * 4"`). Repository fixtures on disk are not mutated.
* **Expected Action Sequence:** `["read_file", "calculate", "write_file"]` with operand `60.0`.
* **Actual Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → `ALLOW`, reads `"15 * 4"`.
  2. `calculate(expression="2 + 3")` proposed with stale value → `ALLOW` (valid arithmetic).
  3. Calculation produces `5.0` instead of `60.0`.
  4. `write_file(path="result.txt", content="5.0")` writes wrong result.
* **Deviation:** An `assertion_failed` event is recorded on calculation input detecting the discrepancy between expected expression (`"15 * 4"`) and actual expression (`"2 + 3"`).
* **Diagnosed Incident:** Member 3 assigns `FailureCategory.STATE_OR_DATAFLOW`.

### 4. `wrong_sequence`
* **Context:** Out-of-order execution where an otherwise permitted write is attempted before calculating the result.
* **Expected Action Sequence:** `["read_file", "calculate", "write_file"]`.
* **Actual Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → `ALLOW`, reads `"15 * 4"`.
  2. `write_file(path="result.txt", content="uncomputed")` proposed before `calculate` has occurred.
  3. With `write_sandbox=True`, safety policy allows the write (`ALLOW`), but the workflow precondition fails.
* **Deviation:** An `assertion_failed` event records the out-of-order `write_file` as the first deviation.
* **Diagnosed Incident:** Member 3 assigns `FailureCategory.PLANNING_OR_TOOL_SEQUENCE`.

---

## 7. Versioned Run-Bundle Contract & Model Specification

### Storage Locations
* **Tracked Starter Fixtures:** `data/fixtures/{scenario_id}.json` (committed to Git for dashboard testing).
* **Real Runtime Run Bundles:** `data/runs/{run_id}.json` (emitted by Member 1's agent; **gitignored** and must never be committed to Git).
* **Dashboard Discovery:** Streamlit dashboard scans and loads run bundles from **both** `data/fixtures/` and `data/runs/`.

### Shared Run-Bundle Model (`src/bifura/schemas/bundle.py`)
Both producer (Member 1) and consumer (Member 2 dashboard & Member 3 learning) validate run bundles using `RunBundle`:

```python
from pydantic import Field
from bifura.schemas.models import (
    Contract,
    DeviationRecord,
    ImpactGraph,
    IncidentMatch,
    IncidentRecord,
    PredictionResult,
    RunRecord,
    SafetyDecisionRecord,
    ToolExecutionResult,
    TraceEvent,
    VerificationReport,
)

class RunBundle(Contract):
    schema_version: str = "1.0"
    scenario_id: str
    run: RunRecord
    expected_action_sequence: list[str] = Field(default_factory=list)
    actual_execution_summary: str = ""
    events: list[TraceEvent] = Field(default_factory=list)
    safety_decisions: list[SafetyDecisionRecord] = Field(default_factory=list)
    execution_results: list[ToolExecutionResult] = Field(default_factory=list)
    deviation: DeviationRecord | None = None
    incident_matches: list[IncidentMatch] | None = None
    incident_records: list[IncidentRecord] | None = None
    prediction: PredictionResult | None = None
    impact_graph: ImpactGraph | None = None
    verification: VerificationReport | None = None
```

### Uncalculated Data Representation & Integration Handoff
1. **Null for Uncalculated Components:** Information that has not been calculated yet must be represented as `None` (`null` in JSON). An empty list `[]` means that a component actually ran and found 0 items.
2. **Initial Bundle (Member 1):** Member 1 produces the initial bundle with `incident_matches: null`, `incident_records: null`, and `prediction: null` because Member 3's learning pipeline has not yet executed.
3. **Integrated Bundle (Member 3):** During integration, Member 3 supplies genuine incident matches, incident records, and prediction results to update the bundle.
4. **Impact Graph:** Member 1 produces the impact graph using explicit event dependencies and data-dependency evidence. The dashboard only visualizes the supplied graph and must not invent causal edges. The impact graph may be `null` if no dependency evidence exists.
5. **Score Semantics Rule:** In `prediction`, heuristic retrieval scores must be explicitly labelled:
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
