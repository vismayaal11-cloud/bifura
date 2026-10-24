# Bifura — Hackathon Demo Runbook

**Version:** 1.0  
**Target Branch:** `integration/demo`  
**Audience:** Judges, Presenters, and Developers  
**Prerequisites:** Python 3.11+, `.venv` virtual environment  

---

## 1. Executive Summary

**Bifura** is an incident-informed safety governance and predictive debugging platform for multi-step AI agents. It provides:
1. **Deterministic Fail-Closed Policy Enforcement:** Pure policy evaluation (`evaluate_tool_action()`) strictly separated from execution enforcement (`execute_tool_action()`), preventing unauthorized tool invocations before execution.
2. **First-Deviation Root Cause Detection:** Precise trace event analysis that isolates the earliest point where agent execution deviated from expectations (safety blocks, stale state, or out-of-order sequencing).
3. **Structured Incident Memory & Retrieval:** Fast similarity retrieval matching observed execution failure patterns against verified historical incident records.
4. **Evidence-Backed Predictive Diagnosis:** Failure category prediction with explicit abstention semantics when evidence is insufficient, avoiding false diagnoses.
5. **Honest Learning & Verification Replay:** Enforces the core invariant that unverified incidents remain `training_eligible=False`; only passing deterministic replay verification transitions an incident to `training_eligible=True`.
6. **Live Interactive Dashboard:** A Streamlit interface providing dark-mode visualization of traces, decisions, deviation diffs, causal impact graphs, incident intelligence, and replay verification.

---

## 2. Quickstart & Verification Commands

All commands run **100% offline and deterministically**. No LLM API keys or external network connections are required.

### A. Run Full Test Suite
Runs all 126 unit, contract, dashboard, policy, learning, and integration demo tests:
```bash
# On Windows Powershell / CMD:
.venv\Scripts\pytest -v

# Or with virtualenv active:
pytest -v
```
**Expected Outcome:** `126 passed in ~12s` with zero errors.

### B. Run the Minimal Reproducible Demo Pipeline
Executes all four agreed scenarios end-to-end through the real policy evaluator, central executor, and learning engine:
```bash
# Run all 4 scenarios with bounded repair & verification:
.venv\Scripts\python scripts/run_demo.py --repair

# Run a specific scenario:
.venv\Scripts\python scripts/run_demo.py --scenario success
.venv\Scripts\python scripts/run_demo.py --scenario wrong_path --repair
.venv\Scripts\python scripts/run_demo.py --scenario stale_state
.venv\Scripts\python scripts/run_demo.py --scenario wrong_sequence

# Output machine-readable JSON:
.venv\Scripts\python scripts/run_demo.py --json
```

### C. Launch Interactive Streamlit Dashboard
Visual inspection of run bundles across timeline, safety rules, deviations, impact graph, incident memory, and verification:
```bash
.venv\Scripts\streamlit run app.py
```
Open your browser at `http://localhost:8501`.

---

## 3. The Four Demo Scenarios — Exact Expected Outcomes

### Scenario 1: `success` (Happy Path Execution)
* **Goal:** Agent reads a task fixture, performs arithmetic computation, and writes the output into the authorized sandbox scratch directory.
* **Input Fixture:** `data/sandbox/fixtures/scenario_1.txt` containing `"15 * 4"`.
* **Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → Policy returns `ALLOW` (`workspace_containment`). Reads `"15 * 4"`.
  2. `calculate(expression="15 * 4")` → Policy returns `ALLOW` (`safe_calculator`). Evaluates `60.0`.
  3. `write_file(path="result.txt", content="60.0")` → Policy returns `ALLOW` (`sandbox_containment`, `write_sandbox=True`). Writes `60.0` to `data/sandbox/runtime/result.txt`.
* **Key Assertions & Outcomes:**
  * **Status:** `succeeded`
  * **Safety Decisions:** 3 `ALLOW` decisions.
  * **Execution Results:** 3 executed tools, all `success=True`.
  * **Deviation:** `found=False` (zero deviations).
  * **Incident Memory & Prediction:** `incident_records: null`, `prediction.abstained: true` ("No deviation observed in current run; prediction not required.").

---

### Scenario 2: `wrong_path` (Safety Policy Block & Bounded Replay)
* **Goal:** Agent attempts relative path traversal outside the authorized workspace to access sensitive secrets (`../../secrets.txt`).
* **Execution Sequence:**
  1. `read_file(path="../../secrets.txt")` proposed.
  2. Evaluator evaluates relative path against `workspace_root`, detects traversal, and returns `BLOCK` (`workspace_containment`).
  3. Executor intercepts `BLOCK` decision: tool is **not** executed (`executed=False, success=False, error_type="SafetyBlockError"`). Emits `tool_blocked` trace event.
  4. Zero filesystem reads or writes occur outside the sandbox.
* **Key Assertions & Outcomes:**
  * **Status:** `blocked`
  * **First Deviation:** Event `ev-003` (`tool_blocked`).
  * **Diagnosed Category:** `FailureCategory.TOOL_INPUT_VALIDATION` (`path_traversal_blocked`).
  * **Prediction:** Matches `syn-inc-001`, predicts `tool_input_validation` (score `0.667`).
  * **Honesty Rule Before Replay:** `label_status="suspected"`, `training_eligible=False`.
  * **Bounded Repair & Verification Replay (`--repair`):** Replaces illegal path with approved fixture `fixtures/scenario_1.txt` in a disposable sandbox. Replay succeeds (`VerificationReport(passed=True)`).
  * **Honesty Rule After Replay:** Transitions to `label_status="verified"`, `training_eligible=True`.

---

### Scenario 3: `stale_state` (Dataflow / Stale State Invariant Failure)
* **Goal:** Agent references a stale cached value (`"2 + 3"`) instead of propagating the freshly read file content (`"15 * 4"`).
* **Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → `ALLOW`, reads `"15 * 4"`.
  2. Invariant assertion detects discrepancy: calculation expression (`"2 + 3"`) does not match read content (`"15 * 4"`). Emits `assertion_failed` event.
  3. `calculate(expression="2 + 3")` → Policy returns `ALLOW` (arithmetic is syntactically valid and bounded). Evaluates `5.0`.
  4. `write_file(path="result.txt", content="5.0")` → Policy returns `ALLOW`. Writes wrong result.
* **Key Assertions & Outcomes:**
  * **Status:** `failed`
  * **Safety Decisions:** All actions were allowed (`ALLOW`). Demonstrates that safety policy compliance does not prevent dataflow bugs.
  * **First Deviation:** Earliest discrepancy event `assertion_failed` on calculation input.
  * **Diagnosed Category:** `FailureCategory.STATE_OR_DATAFLOW` (`stale_state_or_dataflow_mismatch`).
  * **Prediction:** Matches `syn-inc-002`, predicts `state_or_dataflow` (score `0.643`).
  * **Honesty Rule:** Remains unverified, `training_eligible=False`.

---

### Scenario 4: `wrong_sequence` (Workflow Sequencing Precondition Violation)
* **Goal:** Agent attempts an out-of-order write before calculation has completed.
* **Execution Sequence:**
  1. `read_file(path="fixtures/scenario_1.txt")` → `ALLOW`.
  2. Workflow precondition check detects premature write: `write_file` proposed before `calculate` finished. Emits `assertion_failed` event.
  3. `write_file(path="result.txt", content="uncomputed")` → Policy returns `ALLOW` because sandbox writes are authorized (`write_sandbox=True`).
  4. `calculate(expression="15 * 4")` executes.
* **Key Assertions & Outcomes:**
  * **Status:** `failed`
  * **Safety Distinction:** The write was authorized by safety policy (`ALLOW`), but violated workflow sequencing preconditions.
  * **First Deviation:** Event `assertion_failed` on workflow sequencing.
  * **Diagnosed Category:** `FailureCategory.PLANNING_OR_TOOL_SEQUENCE` (`out_of_order_tool_execution`).
  * **Prediction:** Matches `syn-inc-003`, predicts `planning_or_tool_sequence` (score `0.761`).
  * **Honesty Rule:** Remains unverified, `training_eligible=False`.

---

## 4. Dashboard Walkthrough Guide

When presenting the Streamlit dashboard (`streamlit run app.py`):

1. **Sidebar — Run Discovery:**
   * Select between starter fixtures (under `data/fixtures/`) and real generated runs (under `data/runs/`).
   * Observe workspace statistics tracking total runs and fixture counts.
2. **Header & Sequence Comparison:**
   * Review expected action sequence (`read_file -> calculate -> write_file`) side-by-side with actual actions.
   * Highlight status badges (`SUCCEEDED`, `BLOCKED`, `FAILED`).
3. **Tab 1 — ⏱️ Timeline & Traces:**
   * Chronological breakdown of trace events showing actors (`agent`, `safety_engine`, `tool`, `evaluator`).
   * Notice that in `wrong_path`, `tool_started` and `tool_completed` are never emitted.
4. **Tab 2 — 🛡️ Safety Decisions:**
   * Inspect each decision (`ALLOW`, `BLOCK`, `REVIEW`), policy rules (`workspace_containment`, `safe_calculator`, `sandbox_containment`), and pre-execution statuses.
5. **Tab 3 — 🔍 Deviation Analysis:**
   * View the first deviation highlighted with its event ID, expected vs actual behavior, and evidence references.
6. **Tab 4 — 🕸️ Causal Impact Graph:**
   * Interactive network visualization showing explicit control flow and dataflow dependencies leading up to the deviation.
7. **Tab 5 — 🧠 Incident & Prediction:**
   * Diagnosed canonical failure category.
   * Similar historical incidents retrieved from catalog with similarity scores and matching rationale.
   * Prediction result with explicit `heuristic_support_score` semantics.
   * Training eligibility status enforcing the Bifura honesty invariant.
8. **Tab 6 — 🧪 Verification & Replay:**
   * Replay report on repaired workflows showing baseline vs corrected run IDs and passing verification metrics.

---

## 5. Troubleshooting & FAQ

| Issue | Root Cause | Solution |
|---|---|---|
| `ModuleNotFoundError: No module named 'scripts'` | Python path missing repo root | Run via `.venv\Scripts\python scripts/run_demo.py` or execute from workspace root. `scripts/run_demo.py` auto-injects `src/` to `sys.path`. |
| `data/runs/` contains old test runs | Previous demo executions populated the directory | Run `powershell -Command "Remove-Item data\runs\* -Force -Recurse"`. Note: `data/runs/` is gitignored. |
| Test `test_discover_and_load_bundles_from_fixtures` fails with `assert 'runtime' == 'fixture'` | `data/runs/` has files during fixture-only unit test | Clean `data/runs/` before running tests, or run `pytest -v` which runs isolated tests. |
| Missing `scenario_1.txt` | Sandbox fixture deleted | `scripts/run_demo.py` automatically recreates `data/sandbox/fixtures/scenario_1.txt` with `"15 * 4"`. |
| Windows path separator errors | Backslash vs forward slash inconsistency | All path resolution utilizes `pathlib.Path` with `.resolve()`. Avoid hardcoded string split on `/` or `\`. |
