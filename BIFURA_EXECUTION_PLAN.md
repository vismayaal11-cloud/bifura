# BIFURA — Master Execution Plan

**Purpose:** Practical work order for the three-person team and all AI coding assistants  
**Project authority:** `BIFURA_MASTER_PROJECT_SPEC.md`  
**Preparation:** Thursday, October 22 and Friday, October 23, 2026  
**Event:** Saturday, October 24, 2026  
**Buildathon plan:** 10 effective working hours, with a backup demo saved by Hour 8

> **Mandatory instruction:** Every teammate and every AI coding assistant must read `BIFURA_MASTER_PROJECT_SPEC.md` before making changes. This execution plan translates that specification into work. It does not replace it.

---

## 1. Priority and importance — do not change this hierarchy

Bifura has several connected features. They must all be considered, but their roles are different.

### Priority 1 — Main product: autonomous causal debugging

Bifura captures a failed AI-agent execution, compares expected and actual behaviour, finds the earliest evidence-supported deviation, investigates why it happened, traces downstream impact, proposes a bounded fix, and verifies the correction by replay and regression testing.

### Priority 2 — Core speciality: incident-data learning and failure prediction

Bifura retains structured incident records and reviewed fixes, retrieves relevant past cases, predicts likely failure categories from trace/incident features, and evaluates whether training on eligible incidents improves predictions. This is a core capability—not merely a logbook and not just a safety feature.

### Priority 3 — Required feature: safety enforcement engine

**Safety enforcement is secondary to Bifura's product purpose, but it is mandatory implementation scope. Do not omit it, downgrade it to a README note, or substitute a visible warning for real enforcement.** Every proposed investigation or repair tool call must pass through a backend/tool-layer policy engine before execution. The engine must enforce `ALLOW`, `REVIEW`, or `BLOCK`, block prohibited actions before the executor is called, log the result, and pass tests proving that prohibited actions never execute.

### Priority 4 — Dashboard and evidence

The Streamlit interface must show real run traces, deviations, predictions, retrieved incidents, investigation evidence, the impact graph, patch/test/replay results, and safety decisions. UI must display actual backend results, not fake success states.

### The team must not make either of these mistakes

- Do not turn Bifura into a safety-only product.
- Do not treat safety as optional because it is not the main product pitch.

The complete prototype must demonstrate the debugging/learning workflow **and** a functioning safety enforcement path.

---

## 2. Agreed stack and architecture

Use the stack in the master specification:

| Component | Agreed starting point | Role |
|---|---|---|
| Local agent and investigation loop | Python + LangGraph | Plans inspections and investigates evidence |
| LLM | Configurable provider; choose and document an available model | Investigation reasoning and structured tool proposals |
| Prediction | scikit-learn baseline when labelled data supports it | Predict likely failure category from trace/incident features |
| Incident retrieval | Structured filters + explainable similarity matching | Finds relevant prior cases and verified fixes |
| UI | Streamlit | Displays execution, prediction, investigation, graph and verification |
| Impact graph | NetworkX + Plotly | Represents and visualizes dependencies |
| Schemas | Pydantic | Validates run, incident, prediction, tool, policy and report objects |
| Tests | pytest | Verifies trace, prediction, policy, repair and end-to-end workflow |
| Persistence | Local JSON/JSONL + SQLite | Stores traces, incidents, decisions, datasets and reports |

Do not switch to React/FastAPI. That architecture belongs to the separate Agent Autopsy concept.

### Required end-to-end architecture

```text
Local agent under test
       ↓
Trace recorder + expected-outcome assertions
       ↓
Normalized run / event records
       ├─────────────→ Incident store + retrieval
       └─────────────→ Prediction pipeline
                               ↓
                 Autonomous investigation agent
                               ↓
                     Structured tool proposal
                               ↓
                MANDATORY SAFETY ENFORCEMENT GATE
                  ┌────────────┼─────────────┐
                  ↓            ↓             ↓
                BLOCK        REVIEW         ALLOW
             never execute  wait for       execute only
                            authorized      via central
                            resolution      executor
                               ↓
              Evidence gathering + first deviation
                               ↓
                 Root-cause hypotheses + impact graph
                               ↓
                Candidate fix in isolated worktree
                               ↓
                  Safety gate + tests + replay
                               ↓
                 Verified / failed / uncertain report
                               ↓
               Reviewed incident and versioned dataset
                               ↓
                 Candidate model retraining/evaluation
```

The LLM proposes actions; the backend validates and authorizes them. Prediction and incident retrieval may inform which action is useful, but they must never grant permission or override a mandatory safety rule.

---

## 3. Ownership of work

### Member 1 — Agent, trace analysis, tool executor and repair

Owns the local agent-under-test integration, run tracing, expected/actual comparison, first-deviation analysis, LangGraph investigation, restricted tools, central tool executor (`src/bifura/tools/executor.py`) that enforces safety decisions, candidate patching, tests and replay. Member 1 calls the safety policy evaluator but does not duplicate or modify its implementation.

### Member 2 — Safety policy evaluator, dashboard and impact graph

Owns the deterministic safety policy evaluator (`src/bifura/tools/policy.py`) returning `SafetyDecisionRecord`, Streamlit dashboard (`app.py` and `src/bifura/dashboard/`), run overview, timeline, event detail, prediction/incident panels, root-cause evidence, NetworkX/Plotly impact graph, patch diff and before/after verification views, plus mock run bundles in `data/fixtures/`. Member 2 does not modify the executor.

### Member 3 — Incident memory, prediction, evaluation and integration

Owns incident schema, label taxonomy, dataset quality, feature extraction, incident storage, similarity retrieval, baseline model training/evaluation in `src/bifura/learning/`, model/data versioning, the README and cross-module integration coordination.

### Shared responsibility

All three members must understand the end-to-end workflow, inspect actual outputs, run the application, review claims, and help test the complete demonstration. The assigned owner is responsible for implementation; the team is responsible for correctness.

---

## 4. Thursday, October 22 — foundation and minimum safety gate

**Today's goal:** create one working vertical slice and prevent the safety engine from being postponed until the event. Parallel work is okay, but interfaces must be agreed first.

### Task 1 — Create repository, environment and module contracts

**Owner: Member 3**

1. Create a GitHub repository called `bifura` and add both other members.
2. Put `BIFURA_MASTER_PROJECT_SPEC.md` at the repository root.
3. Set up Python, a virtual environment, the agreed dependencies and basic pytest configuration.
4. Create the agreed module structure; keep modules small and real rather than creating empty files for appearance.
5. Define the shared Pydantic contracts before frontend/backend-style parallel work begins.
6. Add README startup instructions and a `.env.example` containing variable names only—never commit secrets.

**Shared minimum record contracts:** `RunRecord`, `TraceEvent`, `DeviationResult`, `IncidentRecord`, `PredictionResult`, `IncidentMatch`, `HypothesisRecord`, `ImpactGraph`, `ToolProposal`, `SafetyDecision`, `ToolExecutionResult`, `PatchRecord`, `TestReport`, and `ReplayReport`.

**Antigravity prompt:**

```text
Read BIFURA_MASTER_PROJECT_SPEC.md completely before coding.

Set up the Bifura repository using Python, LangGraph, Streamlit,
NetworkX, Plotly, Pydantic, pytest, and local JSON/SQLite storage.
Do not use React/FastAPI. Create the initial module structure,
shared Pydantic contracts, a working test configuration, and exact
README setup commands. Keep the architecture consistent with the
master specification. Do not pretend that unimplemented modules
already work. Run the setup tests and report actual results.
```

**Done when:** a teammate can create the environment, start the basic app, and run the initial test command using the README.

### Task 2 — Capture a real execution trace

**Owner: Member 1**

1. Use one small local multi-step agent or controlled practice agent.
2. Instrument tool calls, outputs, relevant intermediate state, errors and final outcome.
3. Define an explicit expected-result assertion or invariant.
4. Save one successful run and one controlled faulty run.
5. Preserve stable run/event IDs and parent/dependency references where known.
6. Keep raw trace and normalized trace linked.

**Antigravity prompt:**

```text
Read BIFURA_MASTER_PROJECT_SPEC.md. Implement the initial local
agent-under-test integration and trace recorder.

Capture the task, expected behavior, tool calls/arguments, results,
state changes, errors and final output using Pydantic schemas. Create
one successful controlled fixture and one deliberately reproducible
faulty fixture. Do not claim the chosen upstream software has bugs
that have not been reproduced. Save actual traces locally and add
pytest coverage for recording and expected-outcome checks.

Do not build the complete investigation agent yet. Report files,
test commands, actual results and limitations.
```

**Done when:** real run events are stored and inspectable, and the expected outcome can be checked.

### Task 3 — Implement the minimum real safety enforcement engine

**Owner: Member 1, reviewed by all three**

This task is mandatory today because all investigation, test, replay and repair tools will use the same enforcement path.

Implement:

- a registered tool catalogue and validated argument schemas;
- trusted backend execution context;
- a central `evaluate_tool_action(proposal, trusted_context)` function;
- `ALLOW`, `REVIEW`, and `BLOCK` decisions with rule and reason;
- one central executor that accepts an action only with a current matching `ALLOW` decision;
- redacted safety event logging with actual execution status; and
- tests proving a blocked proposal cannot reach the executor.

**Minimum prohibited-action cases:** unregistered tool; path traversal/out-of-workspace target; protected secret fixture; arbitrary shell command; unauthorized write outside candidate worktree; direct main/production write or unapproved merge; and a model-generated claim that an untrusted instruction is authorized. Ambiguous authorization must return `REVIEW` and remain unexecuted until resolved.

**Antigravity prompt:**

```text
Implement Bifura's REQUIRED safety enforcement engine as a real
backend/tool-layer gate. It is a supporting feature, not the product
identity, but it is not optional.

Every investigation, test, replay and patch tool proposal must pass
through one central safety gate before tool execution. Resolve trusted
context and authorization in the backend; do not trust LLM-generated
fields such as authorized=true or source=user.

Return ALLOW, REVIEW, or BLOCK with decision ID, policy rule, reason,
redacted evidence and execution status. BLOCK means the executor is
never called. REVIEW means no execution until authorized resolution.
The executor must reject missing, stale, mismatched or non-ALLOW
decisions, including if arguments/target changed after evaluation.

Initially prohibit unregistered tools, arbitrary shell/commands,
paths outside the dedicated sandbox, protected secret-file access,
unauthorized writes, direct main/production writes, and automatic
merge. Incident memory, model predictions and the LLM cannot override
mandatory policies. Use disposable local fixtures only.

Write automated tests for allowed action, unknown tool, path traversal,
protected file access, unauthorized write, shell request, ambiguous
review, spoofed provenance, stale/mismatched ALLOW, and attempted
policy override. Include an integration test through the actual public
agent execution path that proves a prohibited action never reaches a
tool implementation. Do not merely test the policy helper in isolation.
Run tests and report actual evidence.
```

**Done when:** one harmless in-scope operation is allowed and executes; at least one prohibited operation is blocked with executor-call count zero; an ambiguous operation remains unexecuted; decisions appear in logs.

### Task 4 — Create incident schema and seed records

**Owner: Member 3**

Create structured incident records containing the source run, expected/observed behavior, first deviation, category label, diagnosis status, evidence references, affected events, correction, tests/replay, data origin, training eligibility and review status.

Seed the store with:
- the actual controlled failure captured by Member 1; and
- clearly labelled synthetic fixture incidents to exercise the schema and retrieval/training pipeline.

Do not claim synthetic examples are real incidents. Provisional diagnoses must not silently become trusted training labels.

**Done when:** an incident record can be stored and retrieved by ID, with source and verification status visible.

### Task 5 — Dashboard foundation and safety decision visibility

**Owner: Member 2**

Create Streamlit panels for run selection, expected-vs-actual outcome, event timeline, selected-event detail, and a supporting **Tool Execution & Safety Decisions** panel.

The safety panel must show the proposed tool, decision, policy rule, reason, review state and whether the tool actually executed. It must clearly distinguish `BLOCKED — NOT EXECUTED` from execution failure.

**Done when:** it displays the real trace and real safety event from the backend—not hardcoded sample success.

### Task 6 — End-of-day integration test

**Owner: all three**

Run this exact workflow:

1. Start the app and local agent.
2. Record a harmless run.
3. Display its trace in Streamlit.
4. Submit an authorized tool proposal; confirm `ALLOW` and actual execution.
5. Submit a prohibited fixture action; confirm `BLOCK` and executor-call count zero.
6. Confirm both outcomes are logged and shown accurately.
7. Save a working Git commit.

If the safety gate can be bypassed or trace capture is broken, fix this before adding advanced features.

---

## 5. Friday, October 23 — prediction, investigation, impact graph and repair

### Task 7 — Implement first-deviation detection

**Owner: Member 1**

1. Define explicit expected-behavior checks for the controlled failure.
2. Implement `find_first_deviation` against those criteria.
3. Preserve the original event, input/output, relevant state delta and assertion that failed.
4. Distinguish exact findings from hypotheses; do not infer root cause from chronological order alone.
5. Test a healthy run, a known faulty run and an insufficient-evidence case.

**Done when:** the system locates the expected first deviation for the controlled fixture, or explicitly reports that evidence only supports a later point.

### Task 8 — Build the incident training and prediction pipeline

**Owner: Member 3**

1. Freeze a small, unambiguous failure-category taxonomy.
2. Finalize an incident schema, provenance labels and training eligibility rules.
3. Create varied labelled examples. Use verified prototype cases where available and mark synthetic examples clearly.
4. Extract structured features and text features from incident/trace records.
5. Train a scikit-learn baseline if data size/label quality supports it.
6. Compare with a majority-class or simple rules-only baseline.
7. Save dataset version, split assignments, model configuration, model artifact and actual metrics.
8. Ensure related scenario variants do not leak across training and held-out evaluation splits.
9. Provide predictions with category/ranking, score meaning, model/dataset version and retrieved incident references.
10. If evidence is too weak for a valid trained classifier, still implement the reproducible training pipeline with clearly marked synthetic fixtures for a controlled demo; prominently disclose that the dataset is synthetic/small and do not claim production reliability.

**Antigravity prompt:**

```text
Implement Bifura's incident-data, model-training and prediction
subsystem as specified in BIFURA_MASTER_PROJECT_SPEC.md.

Keep incident storage, incident retrieval, supervised model training,
and LLM investigation separate. Use labelled incident/trace features
and a scikit-learn baseline when appropriate. Version the dataset and
model. Prevent duplicate or related examples from crossing splits.
Compare against a simple baseline and save actual evaluation output.
Show whether data is synthetic or from verified local runs.

A retrieved incident is not model training. Do not fine-tune or claim
that the LLM learned unless explicit weight training occurred. Return
predicted categories and scores with honest score semantics, version,
and supporting incident references. Do not invent metrics.
```

**Done when:** an unseen held-out fixture can be passed to the pipeline and receives a prediction from the actual saved model—or a clearly labelled rules/retrieval fallback if the data cannot support a classifier.

### Task 9 — Incident retrieval and the incident-to-learning loop

**Owner: Member 3, with Member 1 integration**

Implement the complete lifecycle:

1. capture failed run;
2. investigate and label root cause;
3. distinguish suspected from verified findings;
4. retain the correction, patch, test and replay evidence;
5. mark the incident training-eligible only after the defined review;
6. create a new versioned dataset containing the approved incident;
7. train a candidate model in a controlled run;
8. evaluate it against the same held-out set and prior baseline; and
9. promote a model only after review of evaluation results.

A match may guide investigation, but cannot prove a cause or authorize an action. The system must show why an incident was retrieved.

**Done when:** one verified incident is traceable from original run to correction and dataset eligibility, and the team can run the versioned training/evaluation command. If the actual model has not been retrained, the UI must say `RETRAINING NOT RUN` rather than imply learning already occurred.

### Task 10 — Build the causal-impact graph

**Owner: Member 2, supported by Member 1**

Use NetworkX and Plotly. Include event/tool/state nodes and explicit dependency edge types such as `invokes`, `returns`, `updates`, `consumes`, `validates`, `suspected_cause` and `affects`.

- Highlight the first deviation.
- Highlight downstream events that consume the faulty output/state.
- Use a visibly different style for inferred links.
- Allow selecting a node/edge to inspect its trace evidence.
- Do not label causality solely from timestamp order.

**Done when:** one controlled scenario shows the deviation and the evidenced downstream impact in the UI.

### Task 11 — Complete the autonomous investigation loop

**Owner: Member 1**

The LangGraph agent should decide what evidence it needs next and choose among restricted tools for trace inspection, state comparison, source inspection, test inspection, incident retrieval, prediction lookup and targeted tests. Predictions and retrieved incidents should prioritize work, not dictate the conclusion.

Every proposed tool action must still pass through the central safety gate. Include an investigation step-budget, timeout and capped retry logic. Stop and report uncertainty when evidence is insufficient.

**Done when:** at least one case makes evidence-dependent inspection choices, logs the observations, revises or rejects a hypothesis when appropriate, and never bypasses safety enforcement.

### Task 12 — Implement bounded patching, tests and replay

**Owner: Member 1**

1. Reproduce and record the faulty baseline.
2. Create an isolated disposable worktree/copy.
3. Propose a minimal patch tied to an investigation hypothesis.
4. Require the safety engine to authorize every file write and command/test action.
5. Run the targeted test before and after the patch.
6. Replay the same controlled task and fixture/tool responses where possible.
7. Run relevant regression tests.
8. Save the patch diff, test report and replay comparison.
9. Require human approval before applying the change to the main project; no automatic production writes or merge.

**Done when:** at least one real controlled failure is corrected and replayed successfully, with the actual diff and test evidence visible in the UI.

### Task 13 — Finish the dashboard integration

**Owner: Member 2**

The dashboard must include:

1. Run overview and expected/actual status.
2. Execution timeline and event inspection.
3. First deviation and evidence.
4. Prediction, model/data version and matching incidents.
5. Root-cause hypotheses and their support/contradiction.
6. Causal-impact graph.
7. Patch diff, tests, replay and before/after result.
8. Incident history and training eligibility.
9. Dataset/model evaluation and retraining status.
10. **Tool Execution & Safety Decisions**: proposed action, `ALLOW`/`REVIEW`/`BLOCK`, reason, policy ID, review status, actual execution status and blocked-action evidence.

The safety panel must be visible and usable, but not dominate the main product landing view. The main narrative remains debugging + incident-informed prediction + verified repair.

**Done when:** every displayed result comes from real application state; pending/unimplemented features are clearly labelled.

### Task 14 — Validate all required failure and policy scenarios

**Owner: all three**

#### Debugging scenarios

Validate three controlled and reproducible fault cases:

- tool-input validation failure;
- incorrect intermediate-state propagation; and
- plan/tool-sequence failure.

If a category cannot be reproduced in the selected local agent, replace it with a fault that can be reproduced. Do not claim these faults already exist upstream until confirmed.

Each case needs a baseline trace, expected failure, first deviation, prediction/retrieved incident output, evidence-backed investigation, impact graph, real fix, passing regression test and replay report.

#### Safety scenarios

Run each through the actual public agent/tool-execution path, not just a unit test of the policy helper:

| Test | Expected behavior | Required proof |
|---|---|---|
| Authorized read inside the sandbox | `ALLOW` | Tool executes and result is logged |
| Unregistered tool | `BLOCK` | Executor call count remains zero |
| Path traversal/out-of-workspace target | `BLOCK` | Executor call count remains zero |
| Protected secret fixture access | `BLOCK` | Executor call count remains zero |
| Arbitrary shell/command request | `BLOCK` | No command runner invoked |
| Unauthorized write outside candidate worktree | `BLOCK` | No write occurs |
| Direct main/production write or unapproved merge | `BLOCK` | No main/production mutation occurs |
| Ambiguous authorization/scope | `REVIEW` | No execution until authorized resolution |
| Spoofed provenance / model says `authorized=true` | Apply trusted backend policy | Model claim does not grant access |
| Proposal modified after an `ALLOW` decision | Reject and reevaluate | Stale/mismatched decision cannot execute |
| Incident memory/prediction/LLM attempts to override mandatory policy | Rule remains enforced | Prohibited operation remains blocked |

**Done when:** the team can show both the core debugging/learning workflow and the safety enforcement feature with actual execution evidence.

---

## 6. Friday end-of-day checklist

- [ ] Agent can run a controlled task and produce trace data.
- [ ] Expected and actual behavior are compared by explicit criteria.
- [ ] First-deviation output includes evidence.
- [ ] Prediction pipeline, label taxonomy and incident retrieval exist.
- [ ] Dataset/model versions and train/test separation are recorded.
- [ ] Causal-impact graph displays at least one controlled failure.
- [ ] Investigation tools make evidence-dependent choices.
- [ ] Every tool proposal goes through the policy engine.
- [ ] A prohibited action is blocked before execution with executor-call count zero.
- [ ] A review-required action remains unexecuted pending authorization.
- [ ] Stale/mismatched `ALLOW` decisions are rejected.
- [ ] At least one bounded fix passes a targeted test and replay.
- [ ] Dashboard displays real predictions, incidents, graph, verification and safety decisions.
- [ ] Three candidate fault cases are validated or their replacement is documented.
- [ ] Safety policy matrix and tests are present in the repository.
- [ ] README works on another teammate's machine.
- [ ] Known-working commit and data fixtures are saved.

If any item is unfinished, mark it honestly and rank it before adding more features.

---

## 7. Saturday, October 24 — 10 effective working hours

| Hour | Primary objective | Required output |
|---|---|---|
| 1 | Rehydrate the working version | App starts; core trace and safety smoke tests pass |
| 2 | Finish first-deviation and evidence display | One clear deviation identified from actual trace |
| 3 | Finish incident prediction/retrieval integration | Prediction and related incident visible with version metadata |
| 4 | Finish safety enforcement and run prohibited-action suite | Blocked operations never reach executor; logs visible |
| 5 | Finish impact graph and investigation evidence | One meaningful dependency-linked case shown |
| 6 | Finish bounded repair and replay | At least one real fix verified with tests/replay |
| 7 | Run held-out prediction evaluation and incident learning workflow | Real metrics, dataset/model versions, limitations recorded |
| **8** | **Record backup demo and save working commit** | **Do not skip this checkpoint** |
| 9 | Resolve critical defects and rerun tests | No known critical regression in core demo path |
| 10 | Rehearse, validate claims and freeze code | Final demo uses only real verified results |

If the project is running behind, do not omit safety enforcement or fake prediction results. Reduce UI polish, reduce extra scenarios, or use a clearly labelled scripted fixture to complete the demonstration, while preserving the real enforcement and honest results.

---

## 8. Three-minute final demonstration

**0:00–0:20 — Problem and Bifura's purpose**  
“An early decision in a multi-step AI-agent run can make execution diverge from the expected result. Bifura uses traces and incident experience to predict likely failures, investigate the cause, show downstream effects and verify the correction.”

**0:20–0:45 — Failed run and deviation**  
Run the controlled task. Show expected vs actual result, the trace, and the first evidence-supported deviation.

**0:45–1:10 — Incident learning and prediction**  
Show the predicted failure category, model/dataset version, the relevant incident, why it matched, and whether the diagnosis is verified. Distinguish a prediction from a proven cause.

**1:10–1:35 — Root cause and impact**  
Show the evidence, source/test reference and the dependency graph. Identify confirmed vs inferred edges.

**1:35–2:05 — Bounded fix and proof**  
Show the candidate patch, targeted regression test, replay, and actual before/after results.

**2:05–2:30 — Safety enforcement demonstration**  
Show one authorized in-scope tool action allowed and executed. Then submit one prohibited tool action; show the `BLOCK` decision, policy reason, log, and proof the executor was never called. If demonstrating `REVIEW`, show that it remains unexecuted before authorized resolution.

**2:30–2:50 — Learning loop**  
Show the reviewed incident's eligibility, dataset version and candidate retraining/evaluation result if genuinely completed. Do not claim automatic/online learning unless the application really does it.

**2:50–3:00 — Measured results**  
Report actual prediction, debugging, replay and policy-test results. Be honest about small or synthetic datasets.

---

## 9. Final release checklist

### Main debugging workflow

- [ ] Actual run and normalized trace saved.
- [ ] Expected-vs-actual comparison works.
- [ ] First deviation links to evidence.
- [ ] Root-cause hypotheses are evidence-referenced and uncertainty-aware.
- [ ] Impact graph separates explicit dependency from inference.
- [ ] Bounded patch is stored in a disposable workspace.
- [ ] Targeted test and replay report actual outcomes.
- [ ] Three reproducible scenarios have real fixes/tests, or unfinished items are disclosed.

### Incident learning and prediction

- [ ] Structured incident records include source and verification status.
- [ ] Verified incidents alone enter the appropriate training set according to policy.
- [ ] Retrieval explains why a case is relevant.
- [ ] A trained baseline model runs when the data supports it; otherwise the fallback is labelled honestly.
- [ ] Dataset/model versions and split information are saved.
- [ ] Held-out metrics are computed by code, not hand-entered.
- [ ] New verified incident can be included in a versioned training cycle, with candidate evaluation before promotion.

### Safety enforcement — required supporting feature

- [ ] Central policy engine returns `ALLOW`, `REVIEW`, or `BLOCK` with rule and reason.
- [ ] Every proposed investigation/repair tool action is intercepted before execution.
- [ ] Unregistered tool, arbitrary command, path traversal, protected-file access and unauthorized writes are blocked.
- [ ] A `REVIEW` action remains unexecuted pending authorized resolution.
- [ ] The executor rejects a missing, stale, mismatched or non-ALLOW decision.
- [ ] LLM output, predictions and incident memories cannot override mandatory safety rules.
- [ ] Prohibited-action integration tests demonstrate executor-call count zero.
- [ ] Safety events are logged and visible in Streamlit.

### Integration and delivery

- [ ] Dashboard uses real backend state.
- [ ] README startup steps work on a teammate's machine.
- [ ] Secrets and private trace data are not accidentally committed or sent externally.
- [ ] Backup demo and known-working commit exist.
- [ ] Every claim in the pitch matches implemented evidence.

---

## 10. Mandatory rules for all AI coding assistants

Give each assistant both files: `BIFURA_MASTER_PROJECT_SPEC.md` and `BIFURA_EXECUTION_PLAN.md`.

```text
Read BIFURA_MASTER_PROJECT_SPEC.md and BIFURA_EXECUTION_PLAN.md before coding.

Bifura's primary purpose is autonomous, incident-informed causal debugging:
capture execution traces, compare expected and actual behavior, locate the
first evidence-supported deviation, predict likely failure categories from
labelled incident data, retrieve relevant verified incidents, investigate
root causes, trace downstream impact, propose bounded fixes, and verify them
using tests and replay.

Incident data, model training/prediction and verified incident reuse are core
features. Do not reduce incident history to passive logging or describe
retrieval alone as model training.

SAFETY ENFORCEMENT IS ALSO A REQUIRED FEATURE. It is secondary to the main
product purpose, but it is not optional. Implement a real central tool-policy
gate that intercepts every investigation/repair tool proposal before
execution and returns ALLOW, REVIEW or BLOCK. Block prohibited actions before
the executor is invoked. Keep REVIEW actions unexecuted until authorization.
Validate trusted context, tool registration, arguments, path scope, permissions,
and patch/test boundaries. Do not trust model-generated authorization claims.
Log decisions and execution status; expose them in the dashboard; include an
integration test proving prohibited actions never reach the executor. Do not
replace this with generic sandbox advice or UI warning text.

The LLM, prediction model and incident retriever cannot override mandatory
safety rules. The executor must reject a missing, stale, mismatched or
non-ALLOW decision. Use disposable fixtures only; do not write to production
or merge candidate patches automatically.

Use the agreed Python/LangGraph/Streamlit/NetworkX/Plotly/Pydantic/pytest and
local JSON/SQLite architecture. Inspect the current repository first. Do not
silently switch to React/FastAPI or create conflicting schemas.

Do not fabricate bugs, predictions, training scores, causal claims, blocked
actions, test passes or verified fixes. Distinguish verified facts from
hypotheses, and synthetic data from real incidents.

Before work, state the assigned module and the contract you will use. After
work, report changed files, actual commands/tests and outputs, remaining
limitations, and the next concrete task. Do not claim a feature works unless
it has actually been tested.
```

---

## 11. Open decisions — record them rather than guessing

The team must decide and document:

- exact LLM provider/model and availability of credentials;
- chosen local agent-under-test/repository;
- the three verified, reproducible failure scenarios;
- frozen failure-category taxonomy;
- amount, source and quality of labelled incident data;
- candidate model selection after data inspection;
- whether partial-run prediction is implemented or remains future work;
- incident review/training-eligibility criteria;
- exact prohibited-action policy matrix for the chosen local tools; and
- measured evaluation values generated by actual scripts.

Until decided, label a point `PROPOSED` or `TBD`. Never let individual AI assistants silently choose incompatible architecture or policy behavior.

---

## Final definition of success

Bifura succeeds when it demonstrates the integrated workflow of **incident-informed prediction + evidence-backed autonomous debugging + downstream impact analysis + bounded repair + verified replay**, while its required safety enforcement engine reliably governs the debugger's own tools and demonstrably blocks prohibited actions before execution.

Debugging and incident learning/prediction define the product. Safety enforcement protects the product's actions. Both must exist in the implementation; neither should be confused with the other.
