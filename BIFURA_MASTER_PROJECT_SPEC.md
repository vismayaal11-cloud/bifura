# BIFURA — Master Project Specification

**Document status:** Authoritative project brief for the team and all AI coding/review agents
**Revision:** Safety enforcement clarified as a mandatory, testable subsystem; debugging and incident learning/prediction remain primary  
**Project category:** Agentic AI / Developer Tools  
**Core domain:** Autonomous causal debugging of multi-step AI-agent executions  
**Primary speciality:** Incident-driven learning and prediction, connected to evidence-backed root-cause investigation, causal-impact analysis, bounded repair, and reproducible verification  
**Working prototype target:** One local AI agent, a small labelled incident dataset, a predictive diagnosis component, an execution/impact visualizer, and three reproducible failure scenarios  
**Default implementation stack:** Python, LangGraph, Streamlit, NetworkX, Plotly, Pydantic, pytest, and local JSON/SQLite data. The team may adjust this only after agreeing on the change and updating this specification.

> **Read this document before designing or coding anything.** It is the single source of truth for Bifura. Do not reinterpret Bifura as a safety-checking product, a malicious-prompt detector, a static trace viewer, or an incident database. Safety controls are supporting guardrails. The core product investigates why an AI agent's execution deviated from its expected result, learns from verified incidents, predicts likely future or recurring failures, traces impact, and verifies fixes.

---

## 1. Executive summary

Bifura is an autonomous debugging agent for AI agents. Given a task, its expected behavior, a failed execution trace, relevant source code, and prior incident data, Bifura should:

1. reconstruct what the agent actually did;
2. compare the actual execution with the expected behavior;
3. locate the earliest observable deviation from the expected path;
4. use evidence to investigate likely root causes;
5. predict likely failure categories/root causes and possible downstream effects using patterns learned from previously labelled incidents;
6. show how the deviation may have affected later actions or state;
7. propose a small, bounded code or prompt correction in an isolated worktree;
8. rerun the same controlled scenario and regression tests; and
9. report what was fixed, what was verified, and what remains uncertain.

Bifura's defining loop is:

**Observe → Compare → Predict → Investigate → Trace Impact → Correct → Replay → Learn from the Verified Incident.**

### Non-negotiable feature priorities

1. **Primary product workflow:** autonomous debugging—capture the run, locate the first deviation, investigate why, trace downstream effects, propose a bounded fix, and verify it.
2. **Core speciality:** incident-driven learning and failure prediction. Structured, reviewed incident data must power a real prediction/evaluation pipeline when the available data supports it; retrieval alone must never be described as model training.
3. **Required safety-enforcement feature:** a server-side/tool-layer policy engine must intercept every proposed tool action and enforce `ALLOW`, `REVIEW`, or `BLOCK` before execution. It must demonstrably block prohibited actions and prevent them from reaching the executor. This is not Bifura's primary product identity, but it is a required working feature—not optional polish or a generic note about sandboxing.
4. **Dashboard and evidence:** the dashboard must expose the debugging workflow, incident/prediction results, repair verification, and a visible tool-execution/safety-decision view.

AI coding assistants must implement all four layers. They must not turn Bifura into a safety-only product, and must not omit the actual enforcement engine because it is secondary to debugging.

Its central question is:

> **“The agent was expected to achieve this result. What did it actually do, where did it first go wrong, why did it happen, what did that mistake affect, and can we prove the correction works?”**

The prediction and incident-learning system is a first-class feature, not a small optional safety feature. The system should preserve a structured history of incidents, use that data to train or update a prediction model, retrieve relevant prior cases, predict likely issues from new or partial traces, and evaluate whether those predictions are useful. The LLM performs investigation and tool orchestration; it should not be described as “trained” merely because the project stores incident records or retrieves similar cases.

## 2. Why the name Bifura?

The name takes inspiration from **bifurcation**: a path splitting into different directions. During a multi-step agent run, a single incorrect decision, bad tool result, or incorrect intermediate state can make subsequent execution diverge from the expected path. Bifura investigates the point of divergence, the steps that depend on it, and the correction needed to return execution to the expected outcome.

**Tagline:** *One mistake. Many consequences. One verified fix.*

## 3. The problem

AI agents complete tasks through sequences of model decisions, tool calls, tool results, observations, and state transitions. A failure at an early step can affect several later steps, so the final wrong answer may be far removed from the original mistake.

For example, a research agent may:

1. read a webpage;
2. extract a value incorrectly;
3. store that value in intermediate state;
4. use the incorrect value in a later tool call; and
5. produce a final report that does not meet the task's expected result.

The final output reveals the failure, but not necessarily where it began or why later steps became incorrect. Bifura aims to connect the final failure to execution evidence, identify the earliest relevant deviation, investigate the likely cause, show downstream dependencies, and verify the repair.

### Problems Bifura targets

- Investigating long traces manually is slow.
- The final incorrect result may hide the first faulty decision.
- Tool results and intermediate state can propagate errors into later actions.
- A trace timeline shows sequence, but sequence alone does not prove causal dependency.
- Similar failures can recur across different runs.
- Engineers can make a plausible fix without proving that the original failure is corrected.
- When an agent has seen many previous failures, that history can help predict recurring failure categories and guide the next investigation—but only if incidents are recorded with useful labels and evidence.

## 4. Product positioning and scope boundaries

### 4.1 What Bifura is

Bifura is an **incident-informed, predictive, evidence-linked debugging agent**. It combines:

- structured execution-trace ingestion;
- expected-versus-actual comparison;
- first-deviation identification;
- incident data and learned failure patterns;
- prediction of likely failure type/root cause from incident data and partial traces;
- retrieval of similar verified incidents;
- evidence-linked root-cause hypotheses;
- a dependency/impact graph;
- bounded code or prompt repair;
- replay and regression verification; and
- a dashboard that presents the investigation and its evidence.

### 4.2 What Bifura is not

Bifura is **not primarily**:

- a safety-policy checker;
- a malicious-prompt detector;
- an incident logbook with no learning or prediction;
- a static trace viewer;
- a general-purpose autonomous coding assistant;
- a product that assumes every event before a failure caused the failure; or
- a system that claims a fix worked without running verification.

### 4.3 Safety controls: supporting purpose, mandatory implementation

Bifura is not primarily a safety-policy product, but safety enforcement is a **required, independently testable feature**. The debugging agent can inspect source code, run tests, and create candidate patches; therefore, unrestricted tool execution would make the core workflow unsafe and unreliable. A general statement such as “use a sandbox” is not enough. The code must include a real policy decision point before tool execution.

The safety engine protects Bifura's own investigation/repair tools (trace/source readers, test runner, replay, and candidate-patch writer). When a test case concerns unsafe behavior by the agent-under-test, Bifura may also capture and analyze that behavior as an incident; this does not make Bifura primarily a policy checker.

The safety engine must:

- intercept **every** proposed investigation/repair tool call before execution;
- validate that the tool is registered and the arguments satisfy its schema;
- resolve authorization and the trusted run/workspace context on the backend, not from model-asserted fields;
- validate resolved paths against the permitted workspace, including traversal attempts;
- enforce permitted actions, allowed targets, execution budgets, and patching boundaries;
- return a structured `ALLOW`, `REVIEW`, or `BLOCK` decision with a reason and relevant policy rule;
- ensure `REVIEW` means no execution until an authorized human resolves the review;
- ensure `BLOCK` means the tool is never invoked;
- prevent the LLM, incident memory, prediction model, or an unapproved rule from overriding a mandatory policy;
- log the decision and actual execution status; and
- include automated tests that spy on or instrument the executor to prove blocked actions never reach it.

At minimum, prohibited actions in the prototype include: unregistered tools; arbitrary shell/command execution; paths outside the dedicated workspace; attempts to read secrets or unrelated files; writes outside an isolated candidate worktree; direct production writes or automatic merge; destructive operations not explicitly permitted by a fixture; and attempts to bypass policy by claiming that an instruction is trusted. The prototype should use disposable local fixtures and fake/controlled tools.

This engine is **not the central pitch or the main UI**. It is nevertheless a required subsystem with its own module, test suite, logs, dashboard evidence, owner and acceptance criteria. Do not omit it or replace it with warning text.

### 4.4 The honest differentiator

Tracing, replay, root-cause diagnosis, fix suggestions, datasets, and regression evaluation already exist in other products. Bifura must not claim that those individual functions are globally novel.

Bifura's intended focus is the integrated workflow:

**Expected behavior → first deviation → incident-informed prediction → evidence-backed investigation → downstream impact → bounded correction → controlled replay → verified incident fed back into the dataset/model.**

The project's strongest proposed distinction is that **incident data is treated as a learning and prediction asset, not just as logs**. Bifura should show the stored incident records, the model/dataset version used, the prediction made, the evidence that supports or contradicts it, the correction that was verified, and how that verified incident is eligible to improve subsequent predictions.

This is a product direction to build and evaluate, not a claim that competitors do not use incident data or improve agents from traces.

---

## 5. End-to-end workflow

### Stage 1 — Capture the run

Capture the user task, success criteria or expected result, agent configuration, model/prompt version when available, tool calls, arguments, results, state changes, errors, timestamps, parent-child relationships, and final output. Preserve raw trace data and a normalized representation.

### Stage 2 — Compare expected and actual behavior

Use explicit assertions, reference outputs, validation rules, or a human-reviewed expected result to decide where actual behavior first violates the expectation. Do not assume that every difference from a previous run is a bug; nondeterministic outputs may be acceptable unless they violate a defined criterion.

### Stage 3 — Predict from incident experience

As soon as enough trace evidence is available, use the prediction component to estimate likely failure category/root-cause class and, where supported, likely affected downstream steps. Prediction can be run:

- on partial traces while an execution is underway, to provide an early warning;
- after a run fails, to rank likely root-cause categories; and
- when a developer opens an incident, to suggest similar cases and likely next inspections.

Predictions must include confidence or calibrated score, the model/dataset version, supporting features or retrieved cases, and an explicit indication that a prediction is a hypothesis—not a verified cause.

### Stage 4 — Investigate using tools

The investigation agent plans the next action based on missing evidence. It may inspect a trace event, a source file, a function, a tool schema, a test, a state transition, or a prior incident. Each observation becomes part of the investigation record. Every tool proposal passes through the mandatory safety engine before execution. The LLM proposes; the trusted backend authorizes and the executor runs only an allowed action.

### Stage 5 — Identify and explain deviation

Report the earliest *evidence-supported* point at which the execution violates an expected condition. Explain why it appears wrong using the task requirement, expected state, observed output, relevant source code, or a test assertion. If evidence is insufficient, report a likely deviation and explain uncertainty.

### Stage 6 — Build the impact graph

Create a graph of execution events and their dependencies. Highlight the suspected root event and downstream events that consume its result or state. Use explicit data lineage or state relationships where available. Use a dashed or otherwise distinct visual treatment for inferred dependencies. Temporal order alone is not enough to label one event the cause of another.

### Stage 7 — Propose a bounded fix

Generate a minimal candidate patch to code, prompt, schema, or agent configuration, depending on the investigated cause. The proposed patch and all file operations pass through the same safety enforcement layer. Apply it only in a disposable branch/worktree after path, scope and policy validation. Record the exact diff and hypothesis the patch is intended to test. Do not merge automatically or write to production. A blocked patch/tool call must not reach the executor; a review-required action remains unexecuted until authorized.

### Stage 8 — Verify

Run targeted tests, regression tests, and replay the original controlled scenario. Compare original and corrected runs. A patch is verified only if the relevant assertions pass and no required regression checks fail. If the model's nondeterminism or external dependencies prevent a reliable comparison, say so and use recorded tool responses or scripted fixtures where possible.

### Stage 9 — Finalize the incident

Record final diagnosis status, evidence, patch, test results, replay result, reviewer decision, and whether the incident is eligible for training. Failed or inconclusive fixes must remain clearly labelled as such.

### Stage 10 — Learn and predict better

Add a completed incident to the labelled learning dataset only when its diagnosis/outcome has been reviewed according to the dataset policy. Version the dataset and prediction model. Re-evaluate on held-out incidents before promoting a new model. On future runs, use the updated model to predict likely failure patterns and guide investigations.

---

## 6. Incident-driven learning and prediction — a core subsystem

This section is central to Bifura. Every implementation plan, UI design, and evaluation plan must include it.

### 6.1 Do not confuse these four things

1. **Incident storage:** saving prior failures and their evidence.
2. **Incident retrieval:** finding earlier cases similar to a current trace.
3. **Predictive model training:** fitting a model to labelled incident examples so it can predict a category or outcome for new inputs.
4. **LLM investigation:** reasoning with the current trace, retrieved incidents, source code, and tests to investigate a specific case.

They complement one another, but they are not interchangeable. If the system only stores incidents or uses similarity search, it must not claim that a machine-learning model was trained.

### 6.2 What does Bifura learn from an incident?

A useful incident should preserve:

- what the agent was trying to do;
- what was expected to happen;
- what actually happened;
- the earliest observed deviation;
- trace/event features that preceded the deviation;
- tool name, argument/result types, state transitions, error signatures, retry count, loop count, and timing where relevant;
- the investigated root-cause category;
- a human-reviewed cause label and evidence references;
- downstream events affected and why the dependency is supported;
- the fix type and patch reference;
- test and replay outcomes;
- confidence and unresolved questions; and
- whether the incident is approved for use in training and evaluation.

Do not store only free-form summaries. The learning pipeline needs structured features and consistent labels, with raw traces retained where permitted.

### 6.3 Prediction tasks

The first prototype should focus on a small number of clear prediction targets instead of trying to predict everything.

**Primary prediction target:** likely failure category/root-cause class from a partial or failed trace.

Example categories to adapt and freeze before dataset creation:

- incorrect tool selection;
- invalid or incomplete tool arguments;
- tool result misinterpretation;
- incorrect intermediate-state update or propagation;
- missing/incorrect step in the plan;
- repeated tool loop or ineffective retry;
- retrieval/input quality problem;
- prompt or instruction-following failure;
- external tool/environment failure; and
- unknown/insufficient evidence.

Only include categories that are clearly defined and represented in the dataset. This is a proposed starter taxonomy, not a claim that these cover all possible agent failures.

**Secondary prediction targets, if data supports them:**

- whether the current execution is likely to fail a defined success criterion;
- which next diagnostic inspection is most useful;
- which prior incident family is likely relevant; and
- which downstream events may be affected by the current deviation.

The system must not produce fake numerical probabilities. If confidence is not calibrated, label scores as model scores or relative rankings, not as true probabilities.

### 6.4 Recommended practical first model

For a hackathon-scale prototype, start with an interpretable classical baseline that can be trained locally on structured and text-derived incident features. For example:

- structured features: tool name, event type, error code, retry count, state-transition flags, schema-validation result, and whether an expected assertion failed;
- text features: trace/event summaries and error messages, converted with a TF-IDF vectorizer;
- classifier: a scikit-learn baseline such as Logistic Regression, or another small model chosen after checking the data size and labels;
- outputs: ranked failure category, model score, and model version.

This is the **proposed MVP approach**, not a requirement to use one algorithm regardless of the dataset. The model selection must be documented and compared with a simple majority-class or rules-only baseline. For a small dataset, a simpler baseline may outperform a complex one.

The LLM should not be presented as trained on incident records unless actual fine-tuning or another explicit weight-training process takes place. For this prototype, the more realistic split is:

- **Prediction model:** trained on structured labelled incident data.
- **Incident retrieval:** returns similar prior incidents with reasons for matching.
- **LLM investigation agent:** uses the trace, predictions, retrieved incidents, repository evidence, and tests to investigate and propose a fix.

### 6.5 Training data requirements

The three required demonstration bugs are not enough to claim robust training or general predictive accuracy. They are end-to-end validation cases. The predictive model needs an appropriately labelled training dataset with multiple examples per failure category.

Build a small, controlled dataset by collecting real prototype runs and generating carefully designed fixture variations. Synthetic examples are allowed for development, but each record must be marked `synthetic` and must never be presented as a real production incident. Avoid near-identical duplicates that leak into both training and test sets.

If the dataset is too small or imbalanced to train a meaningful classifier, show the retrieval/rule-based prediction baseline, report the limitation honestly, and make the trainable pipeline explicit. Do not claim predictive improvement without held-out evaluation evidence.

### 6.6 Incident lifecycle

```text
Run fails or an abnormal pattern is observed
             ↓
Capture the trace, task, expectation and outcome
             ↓
Create an incident record with evidence references
             ↓
Investigate and assign a provisional failure category
             ↓
Verify the cause and correction using code/tests/replay
             ↓
Human-reviewed label and training eligibility
             ↓
Add approved record to a versioned training dataset
             ↓
Train candidate prediction model
             ↓
Evaluate on held-out incidents and compare with baseline
             ↓
Promote model only if predefined criteria are met
             ↓
Use the new model for future predictions
             ↓
Collect outcomes and evaluate again
```

A failed patch, unverified hypothesis, or ambiguous incident can be stored for analysis but must not automatically become a trusted training label. Mark it as provisional and exclude it from the verified training subset unless the learning experiment explicitly supports noisy labels and documents that choice.

### 6.7 Incident retrieval

Alongside model prediction, retrieve related incidents using an explainable first-version method. A candidate score may combine normalized fields, matching tool/event category, error signature, state pattern, and text similarity. Show the fields that caused a match.

Every match should include:

- incident ID and summary;
- matched attributes;
- verified versus provisional status;
- known root cause and supporting evidence;
- correction and associated tests, if available; and
- relevance score or rank, with clear semantics.

Similarity is not proof of causality. The current trace must still be investigated.

### 6.8 How prediction is used in the investigation

The prediction model should guide investigation, not dictate the final conclusion. Example:

1. A partial trace includes repeated invalid tool arguments and a failed schema assertion.
2. The model ranks `invalid_tool_arguments` as the leading failure category.
3. The retrieval component finds a prior verified incident with similar argument-validation evidence.
4. The investigation agent inspects the actual tool schema, proposal, source code, and test output.
5. It may confirm the hypothesis, revise it, or report insufficient evidence.
6. The impact graph shows only dependencies supported by trace/state evidence.
7. A candidate correction is tested and replayed.
8. The incident is only promoted to verified learning data after its outcome is established.

The dashboard must keep these labels distinct: **prediction**, **retrieved prior incident**, **investigation hypothesis**, **verified root cause**, and **verified fix**.

### 6.9 Avoid data leakage and misleading claims

- Split by incident family/scenario where possible, not merely by individual trace rows.
- Keep held-out evaluation incidents out of training, retrieval seeds used for the evaluation, and model selection decisions that inspect test labels.
- Preserve a dataset version and split manifest for each reported score.
- Compare the trained model with an explicit baseline.
- Report class-level precision/recall/F1 and confusion matrix when sample size permits; report raw counts and limitations for small data.
- Track false predictions and `unknown/insufficient evidence` cases.
- Do not say “the agent learns autonomously” if new incidents only enter the store. Say exactly whether the system retrieves, updates rules, retrains a model, or fine-tunes an LLM.
- Do not automatically retrain and promote on every new incident. New records must be validated, model candidates evaluated, and promotion controlled.

---

## 7. Execution traces and data model

### 7.1 Normalized trace event

Use Pydantic schemas to validate trace events. A practical minimum event should include:

```json
{
  "run_id": "run_001",
  "event_id": "event_004",
  "parent_event_id": "event_003",
  "sequence": 4,
  "timestamp": "2026-10-24T10:02:00Z",
  "event_type": "tool_result",
  "agent_node": "research_agent",
  "tool_name": "extract_value",
  "input_ref": "artifact://run_001/event_004/input",
  "output_ref": "artifact://run_001/event_004/output",
  "state_before_ref": "artifact://run_001/state/003",
  "state_after_ref": "artifact://run_001/state/004",
  "status": "success",
  "error_type": null,
  "assertions": [],
  "source_location": null,
  "data_dependencies": ["event_003"],
  "metadata": {"fixture": true}
}
```

This JSON is an illustrative schema, not an actual captured run. Avoid putting extremely large prompts/results directly in graph nodes; use artifact references where practical. Redact secrets and sensitive data.

### 7.2 Incident record

Each incident should store at least:

```json
{
  "incident_id": "incident_001",
  "run_id": "run_001",
  "title": "Intermediate value was misinterpreted",
  "expected_behavior": "The report uses the extracted value unchanged",
  "observed_behavior": "A later step uses a transformed value",
  "first_deviation_event_id": "event_004",
  "failure_category": "incorrect_intermediate_state",
  "label_status": "verified",
  "root_cause_summary": "The state update applies the wrong conversion",
  "evidence_event_ids": ["event_004", "event_005"],
  "affected_event_ids": ["event_005", "event_006"],
  "dependency_evidence": ["state value from event_004 is consumed by event_005"],
  "fix_ref": "patches/incident_001.diff",
  "test_refs": ["tests/test_incident_001.py"],
  "replay_status": "passed",
  "data_origin": "fixture",
  "training_eligible": true,
  "review_status": "approved"
}
```

The example is illustrative. In real records, only use `verified`, `training_eligible: true`, or `replay_status: passed` if that status is supported by actual verification.

### 7.3 Data stores

For the local prototype, use:

- JSONL or JSON for event traces and fixture data;
- SQLite or structured JSON for incident records and investigation state;
- versioned JSON/CSV files or SQLite tables for labelled training data;
- versioned model artifacts and a small metadata manifest for model versions;
- patch files and test/replay reports stored alongside the corresponding incident.

The team may use SQLite for all structured records if it simplifies implementation. Raw trace artifacts should be separated from summary/index data where useful.

### 7.4 Minimum incident fields

`incident_id`, `run_id`, `task_summary`, `expected_behavior`, `observed_behavior`, `first_deviation_event_id`, `failure_category`, `label_status`, `root_cause_hypotheses`, `verified_root_cause`, `evidence_refs`, `affected_event_ids`, `fix_ref`, `test_refs`, `replay_status`, `data_origin`, `training_eligible`, `review_status`, `created_at`, and `dataset_version`.

---

## 8. Causal-impact graph

The graph is intended to show **why later behavior was affected**, not just what happened next in time.

### Nodes

- task/requirement;
- agent reasoning/decision event, when observable;
- tool invocation;
- tool result;
- state update;
- validation/assertion;
- error or deviation;
- source-code location; and
- final output.

### Edges

- `invokes`: a decision invokes a tool;
- `returns`: a tool invocation produces a result;
- `updates`: an event updates state;
- `consumes`: a later event consumes prior data/state;
- `validates`: a test/assertion checks an event or outcome;
- `suspected_cause`: a hypothesis links a candidate cause to an observed failure; and
- `affects`: a dependency-supported event may affect a downstream event.

Use solid edges for recorded/explicit relationships and a distinct dashed style for inferred relationships. Do not present a `suspected_cause` edge as confirmed causality until evidence supports it. Give the user a way to inspect the evidence behind a highlighted edge.

### Expected graph interaction

Selecting the first deviation should highlight the event, show its input/output and state delta, surface the relevant source/test location, and highlight known downstream consumers. Selecting a downstream event should let the user trace back to the state or tool result it consumed.

---

## 9. The autonomous investigation agent

The investigation agent uses an LLM to plan and carry out the next diagnostic action. The LLM is not the prediction model itself unless the implementation explicitly uses it for that role. Keep these components separate in code and in the documentation.

### Agent input

- the user's debugging task;
- success criteria or expected behavior;
- normalized trace and relevant artifacts;
- prediction outputs and uncertainty;
- retrieved incident records;
- repository and test context; and
- allowed tool registry and action budget.

### Agent tools

Initial recommended tools:

- `get_run_summary(run_id)`;
- `get_trace_event(event_id)`;
- `get_state_diff(event_a, event_b)`;
- `search_trace(query_or_filter)`;
- `inspect_source_file(path, line_range)`;
- `search_repository(query)`;
- `inspect_test(test_ref)`;
- `run_targeted_test(test_ref)`;
- `retrieve_incidents(filters)`;
- `get_prediction(run_id_or_trace_prefix)`;
- `create_candidate_patch(diff)`;
- `replay_run(run_id, fixture_version)`; and
- `record_investigation_finding(finding)`.

The actual first implementation can be smaller. Tools must return structured outputs and record their own execution events.

### Agent loop

1. Determine what is known and what evidence is missing.
2. Choose the smallest useful next inspection.
3. Execute the inspection through the restricted tool layer.
4. append the resulting evidence to the investigation state;
5. update the cause hypotheses and confidence/strength of evidence;
6. determine whether another inspection is needed;
7. propose a bounded patch only when sufficient evidence exists;
8. run tests and replay;
9. report verified results or stop with uncertainty.

Use a bounded step budget, retry budget, and tool timeout. The agent must be able to stop when there is not enough evidence. A fixed scripted workflow is acceptable as a fallback/demo mode, but it must be labelled as scripted and must not be presented as autonomous reasoning.

### Hypothesis record

A hypothesis should include:

- `hypothesis_id`;
- candidate cause/category;
- supporting evidence references;
- contradicting evidence references;
- prediction score or confidence label, with its source;
- status (`candidate`, `supported`, `rejected`, or `verified`); and
- next experiment/inspection that could distinguish it from alternatives.

The agent must not invent evidence references or claim that source code was inspected when it was not.

---

## 10. Bounded patching and replay

### Patch constraints

- Work only in a disposable local worktree or copy.
- Limit changes to relevant source files, prompts, schemas, or tests.
- Save the diff and link it to the hypothesis being tested.
- Never write to production or merge automatically.
- Do not execute arbitrary commands supplied by the LLM without validation.
- Require human review before any patch is applied to the main project.

### Verification workflow

For each failure case:

1. Run the faulty baseline and save its trace and expected failure.
2. Verify that the failure is reproducible under recorded/controlled conditions.
3. Run the relevant targeted test before the fix and preserve its failure.
4. Apply the candidate patch in the isolated worktree.
5. Run the targeted regression test.
6. Replay the original scenario using the same fixture/tool results where possible.
7. Run relevant broader regression tests.
8. Compare key states, outputs, and assertions.
9. mark the fix as verified only if the defined criteria pass.
10. retain evidence of failed tests if the patch does not work.

If a fix fails, the agent may inspect the test failure and perform a small, capped retry. If evidence remains ambiguous or the budget is reached, it must stop and report uncertainty rather than endlessly patching.

### Required safety enforcement engine (not optional)

The safety engine is an explicit subsystem used by investigation, test-running, replay, and patch tools. Its responsibility is to prevent prohibited tool actions from executing while allowing authorized, bounded debugging work to proceed.

#### Decision contract

`evaluate_tool_action(proposal, trusted_context) -> SafetyDecision` must return at least:

- `decision_id`, `run_id`, and `proposal_id`;
- `decision`: `ALLOW`, `REVIEW`, or `BLOCK`;
- `tool_name` and normalized/validated target where safe to record;
- `policy_rule_id` and human-readable reason;
- evidence/context references used by the decision; and
- execution status (`not_started`, `awaiting_review`, `blocked`, `executed`, or `failed`).

Do not store secrets or sensitive raw argument values in logs. Preserve enough redacted evidence to make each decision auditable.

#### Mandatory enforcement sequence

1. Parse and validate the proposed action against the registered tool schema.
2. Resolve the trusted task, workspace, actor permissions and instruction provenance in backend orchestration. Never trust an LLM-generated `authorized`, `trusted`, or equivalent flag.
3. Validate operation-specific permissions and resolve/normalize any path.
4. Apply mandatory policy rules, including prohibited-tool, prohibited-path, prohibited-write, and budget checks.
5. If the action violates a mandatory rule, return `BLOCK` and do not call the executor.
6. If authorization or scope is ambiguous, return `REVIEW` and do not execute until authorized review resolves it.
7. Return `ALLOW` only when checks pass; execute through the central executor, then record the actual result.
8. Store the decision and actual execution state. A UI warning without backend enforcement does not count.

#### Minimum prohibited-action test matrix

- Unregistered tool name → `BLOCK`; executor call count remains zero.
- Out-of-workspace path and traversal path → `BLOCK`; executor call count remains zero.
- Attempt to read a protected/secret fixture → `BLOCK`; executor call count remains zero.
- Direct production/main-worktree write or unapproved merge → `BLOCK`.
- Arbitrary shell or command execution not in the allowlist → `BLOCK`.
- Ambiguous operation requiring additional authorization → `REVIEW`; executor call count remains zero until approval.
- Authorized read inside the permitted fixture workspace → `ALLOW`; action executes and result is recorded.
- Model claims that an untrusted instruction is authorized → backend policy still blocks/reviews based on trusted context.
- Attempts to make the prediction model, incident memory, or LLM override a mandatory rule → mandatory rule remains in force.
- Changed proposal, stale decision, mismatched target, or policy-version mismatch → executor rejects the action; require a fresh safety decision.

The tests must exercise the central execution function, not merely test the decision helper in isolation. At least one integration test must assert that a prohibited proposal cannot reach any tool implementation through any public agent execution path.

### What safety is—and is not—in the product

Safety enforcement is a **secondary product capability but a mandatory implementation requirement**. It must have working policy code, enforcement, test coverage, audit events, and a dashboard view. It must not consume the majority of the demo or replace incident-informed debugging, prediction and verified repair as the main story.

---

## 11. Technology stack and architecture

### Default stack from the current Bifura proposal

| Layer | Proposed technology | Responsibility |
|---|---|---|
| Agent orchestration | Python + LangGraph | Bounded plan/inspect/act/observe loop |
| LLM provider | Configurable provider, exact model TBD | Investigation reasoning and structured tool proposals |
| Prediction model | scikit-learn baseline, selected after inspecting labelled data | Predict likely failure category from trace/incident features |
| Incident retrieval | Structured filters + explainable similarity baseline | Retrieve similar past incidents and verified fixes |
| Dashboard | Streamlit | Run selection, timeline, hypotheses, impact graph, incident/prediction panels, patch/test report |
| Graph construction | NetworkX | Build execution dependency and impact graph |
| Graph visualization | Plotly | Interactive timeline/graph and before-after views |
| Schemas | Pydantic | Validate event, incident, hypothesis, and tool data |
| Tests | pytest | Regression, dataset, prediction, integration and replay tests |
| Local persistence | JSON/JSONL and SQLite | Traces, incidents, runs, data versions and reports |
| Source control | Git | Version source, patches, fixtures and docs |

Do not silently switch to React/FastAPI from the separate Agent Autopsy project. If the team intentionally changes Bifura's stack, document why, update the interface contract, and keep one agreed architecture.

### Architecture

```text
Local agent under test
        |
        v
Trace instrumentation / fixture recorder
        |
        v
Normalized run events + expected-behavior checks
        |
        +--------------------------+
        |                          |
        v                          v
Incident data + retrieval     Prediction pipeline
        |                          |
        +------------+-------------+
                     v
          Autonomous investigation agent
                     |
                     v
        Structured tool proposal
                     |
                     v
      MANDATORY SAFETY ENFORCEMENT GATE
      validate tool / context / scope / permissions
           |          |             |
           v          v             v
        BLOCK       REVIEW         ALLOW
      no execute   wait for       execute only via
                   approval       central executor
                                      |
                                      v
                inspect trace/source/tests, build impact graph
                                      |
                                      v
                         Candidate patch in isolated worktree
                                      |
                                      v
                           Safety gate checks write/test/replay
                                      |
                                      v
                         Targeted tests + replay + comparison
                                      |
                                      v
                       Reviewed incident and verification record
                                      |
                                      v
                          Versioned dataset / model evaluation
                                      |
                                      v
                       Prediction model for future investigations
```

The safety/permission layer wraps agent tools and candidate patching as infrastructure. It is not the main reasoning or product layer, but the gate is mandatory and its enforcement must be tested. No tool proposal may jump directly from the LLM to a tool implementation.

---

## 12. Suggested repository layout

```text
bifura/
├── app.py                         # Streamlit entry point
├── pyproject.toml                 # Dependencies and tooling
├── README.md
├── .env.example                   # Names of required environment variables; no secrets
├── .gitignore
├── src/
│   └── bifura/
│       ├── agent/
│       │   ├── graph.py           # LangGraph investigation workflow
│       │   ├── prompts.py
│       │   └── state.py
│       ├── tracing/
│       │   ├── schemas.py         # Pydantic event schemas
│       │   ├── ingest.py
│       │   ├── normalize.py
│       │   └── replay.py
│       ├── analysis/
│       │   ├── deviation.py       # Expected-vs-actual / first deviation
│       │   ├── hypotheses.py
│       │   ├── impact_graph.py    # NetworkX construction
│       │   └── evidence.py
│       ├── learning/
│       │   ├── incident_store.py
│       │   ├── features.py
│       │   ├── retrieve.py
│       │   ├── train.py
│       │   ├── predict.py
│       │   ├── evaluate.py
│       │   └── model_registry.py
│       ├── repair/
│       │   ├── patching.py
│       │   ├── test_runner.py
│       │   └── verification.py
│       └── tools/
│           ├── registry.py
│           ├── restricted_tools.py
│           ├── policy.py            # Mandatory ALLOW/REVIEW/BLOCK enforcement
│           ├── executor.py          # Only route from proposals to tool execution
│           └── safety_log.py        # Redacted, auditable decisions/outcomes
├── data/
│   ├── fixtures/
│   ├── traces/
│   ├── incidents/
│   ├── training/
│   └── evaluation/
├── models/                        # Local model artifacts; large files may be gitignored
├── patches/                       # Candidate diffs from controlled test runs
├── results/                       # Versioned evaluation and replay reports
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── prediction/
│   ├── replay/
│   ├── safety/
│   │   ├── test_allowed_action.py
│   │   ├── test_prohibited_actions.py
│   │   ├── test_review_and_approval.py
│   │   └── test_no_executor_bypass.py
│   └── regression/
└── docs/
    ├── architecture.md
    ├── incident_schema.md
    ├── prediction_evaluation.md
    ├── policy_and_sandbox.md
    └── demo_script.md
```

This structure is a recommended starting point. Keep code modular, but do not create empty modules purely to match the tree. Build the smallest useful vertical slice first.

---

## 13. Streamlit dashboard requirements

The dashboard must communicate the investigation clearly. Use a restrained, professional developer-tool design with hierarchy, legible typography, consistent spacing, meaningful charts, and clear status labels. Avoid decorative visuals that obscure evidence.

### Screen/panel A — Run overview

Show task, expected outcome, actual outcome, final status, selected run, model/prompt version where available, and links to the run trace and fixture version.

### Panel B — Execution timeline

Show each decision, tool call, tool result, state change, assertion, and error in sequence. The user must be able to select an event and inspect inputs, outputs, and relevant state.

### Panel C — Prediction and learned incidents

Show:

- predicted failure category/root-cause classes ranked by score;
- timing of the prediction (partial trace or completed run);
- prediction model and dataset version;
- relevant incident matches and why they match;
- whether each retrieved incident's diagnosis is verified or provisional; and
- actual outcome when it becomes known.

Clearly separate prediction from verified diagnosis. Do not display model scores as calibrated probabilities unless calibration was measured.

### Panel D — Root-cause investigation

Show the first suspected deviation, ranked hypotheses, supporting and contradicting evidence, source-code locations, and the next inspection/experiment selected by the agent. Permit marking a diagnosis as verified, rejected, or unresolved with a reason.

### Panel E — Causal-impact graph

Use NetworkX and Plotly to show the first deviation and affected downstream events. Distinguish recorded dependencies from inferred hypotheses. Selecting graph elements should expose the corresponding trace evidence.

### Panel F — Patch and verification

Show patch diff, affected files, test list, original failure, replay result, before/after output, and regression-test results. Clearly indicate if a patch failed or has not been verified.

### Panel G — Incident and dataset management

Show incident records, label status, training eligibility, dataset version, train/validation/test assignment, model versions, and the last evaluation report. Do not let held-out evaluation cases accidentally enter training.

### Panel H — Tool execution and safety enforcement (required supporting feature)

Show proposed tool actions, the server-side `ALLOW`/`REVIEW`/`BLOCK` decision, the applicable rule, redacted evidence/reason, review state, and actual execution status. Make it visually clear that a blocked action was not executed. Include a safe demonstration of one prohibited action being blocked and one authorized action being allowed. This is an audit/control panel, not the primary landing page or main product pitch.

### Required UX states

Include loading, empty, error, no-prediction, insufficient-evidence, and test-failure states. Label fixtures/demo data as sample data. No hardcoded “success” indicators for tests or patches.

---

## 14. API/function contracts

For the first local prototype, function calls are acceptable; an HTTP API is not required unless the team deliberately chooses it. Maintain equivalent clear contracts.

Recommended core functions:

- `ingest_run(raw_trace, expected_behavior) -> RunRecord`
- `normalize_trace(run_record) -> list[TraceEvent]`
- `find_first_deviation(run, expectations) -> DeviationResult`
- `extract_features(run_or_prefix) -> FeatureVector`
- `predict_failure(feature_vector, model_version) -> PredictionResult`
- `retrieve_similar_incidents(feature_vector, incident_store) -> list[IncidentMatch]`
- `investigate_run(run_id, budget) -> InvestigationRecord`
- `build_impact_graph(run_id, deviation_id) -> ImpactGraph`
- `propose_patch(hypothesis_id, workspace) -> PatchRecord`
- `run_regression_tests(patch_id, test_refs) -> TestReport`
- `replay_run(run_id, fixture_version) -> ReplayReport`
- `finalize_incident(incident_id, review) -> IncidentRecord`
- `train_candidate_model(dataset_version, config) -> ModelArtifact`
- `evaluate_model(model_version, split_version) -> ModelEvaluation`
- `promote_model(model_version, evaluation_id, approval) -> ModelRegistryRecord`
- `evaluate_tool_action(proposal, trusted_context) -> SafetyDecision`
- `execute_allowed_action(proposal, safety_decision) -> ToolExecutionResult` (must reject a missing, stale, or non-ALLOW decision)
- `resolve_review(decision_id, reviewer, outcome) -> SafetyDecision`
- `get_safety_events(run_id) -> list[SafetyDecision]`

All returned records must include stable IDs and statuses. The central executor must not accept raw LLM proposals as executable instructions; it must verify a current `ALLOW` decision bound to the exact proposal, trusted context, policy version and target. A decision for a different or modified proposal is invalid. Tool errors and safety decisions must be structured and logged. Never pretend a function completed successfully without its actual result.

---

## 15. Evaluation plan and success criteria

Bifura needs separate evaluations for debugging quality, prediction quality, impact graph quality, and fix verification.

### 15.1 Required reproducible failure scenarios

The team must create and validate three fault cases in a local practice agent. They are not claimed to exist in upstream code until reproduced and inspected. Suggested categories:

1. **Tool-input validation failure:** a malformed, incomplete, or mismatched tool argument causes a downstream failure.
2. **Incorrect intermediate-state propagation:** an incorrect or stale intermediate value affects later steps.
3. **Plan/tool sequence failure:** a missing, repeated, or inappropriate step causes the run to fail its expected outcome.

These are candidate scenarios. The team must confirm they can be triggered in the selected local agent, document their actual causes, fix the code, and demonstrate passing regression tests. Replace a category if it is not reproducible.

### 15.2 Prediction evaluation

Use labelled incident records with explicit train/validation/test splits. Report:

- number of records per split and per category;
- macro-F1 and per-class precision/recall where sample size allows;
- confusion matrix;
- top-k accuracy if multiple ranked root-cause hypotheses are returned;
- performance on partial traces versus completed traces, if both modes are implemented;
- baseline performance (e.g., majority class or simple rules);
- model and dataset versions; and
- known limitations, especially small sample size and synthetic data.

For a tiny dataset, raw counts matter more than impressive-looking percentages. Do not claim a reliable prediction model based on three demonstration bugs alone.

### 15.3 Debugging workflow evaluation

For each of the three scenarios, measure whether Bifura:

- detects the expected failure;
- identifies the earliest known deviation (or marks a later point if evidence supports only that point);
- proposes a root-cause hypothesis supported by actual trace/source/test evidence;
- correctly identifies known downstream dependencies;
- produces a patch that resolves the defined failure; and
- passes the relevant regression test on replay.

Keep the original trace, investigation record, patch, test report, and replay result so the demonstration is reproducible.

### 15.4 Incident-learning evaluation

Test whether verified past incidents improve prediction or investigation compared with the same system without incident information. Use the same held-out cases, freeze the base configuration, and compare:

- prediction quality with the baseline and with incident features enabled;
- quality of retrieved cases;
- whether the right diagnostic tool/test is selected;
- false alarms on harmless/healthy runs;
- whether the model's prediction changes appropriately when new evidence arrives; and
- whether a newly verified incident improves a later held-out evaluation after retraining.

Do not use the held-out test set to create incident examples or tune model configuration. An incident retrieval result appearing in the UI is not evidence of predictive improvement by itself.

### 15.5 Fix-verification metrics

Report targeted test pass/fail, replay pass/fail, regression test pass rate, unresolved failures, and whether the corrected execution meets the specified expected behavior. Preserve failing patch results as well as successes.

### 15.6 Safety-enforcement evaluation (required feature)

Safety must be tested as an enforcement mechanism, not just as a conceptual guardrail. Create a policy matrix and automated tests for:

- allowed action inside the sandbox;
- prohibited/unregistered tool;
- path traversal and outside-workspace target;
- protected/secret-file access;
- unauthorized write, production/main-worktree write, or unapproved merge;
- arbitrary command/shell request;
- ambiguous action that must be held for review;
- spoofed instruction provenance or model-generated authorization claims; and
- attempted policy override by incident memory, prediction or LLM output.

For every blocked case, record the decision and prove the executor was not called. For review-required cases, prove no execution occurs before approval. For allowed cases, verify the action runs only within its authorized scope. Include an end-to-end integration test through the real public agent/tool path to show there is no bypass route.

Report counts of allowed, reviewed and blocked cases, executor-call assertions, policy-test failures, and unresolved risks. Do not present this as a general security certification; it is prototype-level enforcement evidence.

### 15.7 Definition of a credible success claim

A credible claim is one the team can show in the actual application with retained artifacts. For example: “On our labelled held-out fixture set of N incidents, this model achieved X macro-F1 compared with Y for our baseline.” Only use values measured by the actual evaluation script. Do not substitute planned targets or example numbers for results.

---

## 16. Data quality, review, and governance

- Keep raw trace, normalized event, incident, and model-training data linked by IDs.
- Record data origin (`real_local_run`, `synthetic_fixture`, or another explicit source).
- Label each diagnosis as provisional, reviewed, or verified.
- Only incidents eligible under the dataset policy may train the verified-label model.
- Keep a separate held-out evaluation set.
- Version training data, feature extraction logic, model settings, and artifacts.
- Record which dataset/model produced each prediction.
- Store the patch, test result, replay result, and reviewer decision with the incident.
- Redact API keys, credentials, private user data and secrets from traces.
- Do not send repository content or traces to an external LLM provider unless the configuration and user consent permit it.
- If an incident is later relabelled, preserve the original label history and create a new dataset/model version rather than silently overwriting reported metrics.

---

## 17. Model and LLM configuration

The exact LLM provider/model is not finalized in this specification. Keep provider configuration isolated behind an adapter. The model must support structured output or have a robust validation/parsing layer.

### Configuration expectations

- Provider and model names are configured outside source code.
- Credentials are stored in environment variables or a local secrets mechanism and never committed.
- Model prompts and versions are recorded for reproducibility.
- Handle timeouts, rate limits, invalid JSON, refusals, provider outages, and tool-call errors.
- Use deterministic/scripted fixtures for repeatable tests and a demo fallback.
- The script/fallback path must still generate genuine trace, prediction, graph, and test data through the same application flow; it must not fake successful patch verification.

### Component separation

- The **LLM** reasons over the task, available evidence, retrieved incidents, code, tests, and model prediction.
- The **investigation agent** orchestrates the multi-step plan and tools.
- The **prediction model** is a separately trained model that predicts failure categories from labelled incident/trace data.
- The **incident retriever** returns related historical cases and explains why they match.
- The **impact graph** represents known and inferred dependencies.
- The **patch/test/replay subsystem** tests whether the proposed fix restores expected behavior.

Keep these roles distinct in source files, architecture, and dashboard labels.

---

## 18. Existing solutions and competitive positioning

Bifura enters an active ecosystem. Its proposal must acknowledge related products and focus its claim on the integrated workflow and a measured result.

### LangSmith Engine

LangSmith Engine, announced by LangChain in May 2026, clusters recurring agent failures, diagnoses root causes using trace data and source code, proposes fixes, and can turn failures into evaluation/dataset examples. In September 2026, LangChain described additional red-team and automated testing improvements. This is a close competitor. Bifura must not claim that incident clustering, root-cause analysis, fix proposals, or evaluation generation are unique features.

Official references:
- https://www.langchain.com/blog/introducing-langsmith-engine
- https://www.langchain.com/blog/how-we-built-langsmith-engine-our-agent-for-improving-agents
- https://www.langchain.com/blog/langsmith-engine-v2-redteam

### LangSmith Studio

LangSmith Studio provides a visual interface for inspecting local agent runs, prompts, tool calls/results, intermediate state, and replaying a run from a step.

Official reference:
- https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/studio.mdx

### Arize Phoenix

Phoenix is an open-source AI observability/evaluation platform that supports tracing, experiments, datasets and evaluation, replaying traced calls, and AI-assisted debugging through Phoenix Intelligence.

Official references:
- https://github.com/Arize-ai/phoenix/
- https://arize.com/phoenix/

### Chidori

Chidori documents record/replay using recorded host-call results and deterministic fixtures, including converting runs into repeatable verification tests. This means replay alone is not a unique differentiator.

Official reference:
- https://github.com/ThousandBirdsInc/chidori/blob/main/docs/replay.md

### Competitive claim for Bifura

Use this careful phrasing:

> “Bifura focuses on a reproducible, incident-informed debugging loop for a local tool-using agent: predict likely failure patterns from labelled incident history, identify the earliest evidence-supported deviation, trace downstream dependencies, investigate source and test evidence, apply a bounded correction, and replay the same controlled scenario to verify the result. We evaluate the predictive contribution of incident data separately from the debugging and repair workflow.”

This is a proposed product focus, not proof that no other platform has similar capabilities. The team must demonstrate the contribution with measured results and avoid unqualified “first”, “only”, or “unique” claims.

---

## 19. Hackathon implementation plan

The core is a working vertical slice; do not implement every future feature before the first end-to-end run works.

### Phase A — Foundation plus minimum safety enforcement

1. Create the repository and Python environment.
2. Install LangGraph, Streamlit, NetworkX, Plotly, Pydantic, pytest and the chosen prediction/data dependencies.
3. Create one small, local agent under test and capture structured trace events with an expected outcome.
4. Create the registered-tool interface and a central executor. No agent tool can execute directly.
5. Implement the initial policy decision contract (`ALLOW`, `REVIEW`, `BLOCK`) and a small policy matrix.
6. Include one allowed fixture operation and one clearly prohibited operation; prove the prohibited operation never calls the executor.
7. Render one run timeline.

**Done when:** the team can run the local agent, capture and display a real trace, allow an authorized fixture action, and block a prohibited action before execution. Do not postpone safety enforcement until the end, because the investigation agent uses tools from the beginning.

### Phase B — First deviation and dependency graph

1. Define expected-behavior assertions.
2. Implement first-deviation detection for the controlled fixture.
3. Record event/state dependencies.
4. Build the NetworkX graph and Plotly visualization.
5. Show the first deviation and known downstream consumers.

**Done when:** the application highlights the actual failing event and explains the evidence behind the graph edges.

### Phase C — Incident data and prediction

1. Define a small, frozen failure-category taxonomy.
2. Design incident and dataset schemas.
3. Add reviewed/synthetic labels and source metadata.
4. Seed enough varied, labelled fixtures for a baseline experiment; mark synthetic data clearly.
5. Train a local baseline model if the dataset supports it; otherwise ship the retrieval/rules baseline and document the limitation.
6. Add a prediction result panel that displays category, score, model version and relevant prior cases.
7. Create separate train/validation/test splits and an evaluation script.

**Done when:** prediction is generated from a documented model/data or clearly labelled baseline, and actual measured results are saved.

### Phase D — Agentic investigation with enforced tool permissions

1. Use LangGraph to plan diagnostic actions.
2. Add tools to inspect trace events, state differences, source, tests, and incident history.
3. Route every proposed action through the mandatory safety engine before execution.
4. Use prediction and incident retrieval to prioritize investigation, not to dictate conclusions.
5. Record hypotheses and supporting/contradicting evidence.
6. Respect permissions, workspace boundaries, tool/time budgets, and stop when evidence is insufficient.
7. Test allowed, blocked and review-required actions through the public execution path.

**Done when:** the agent selects evidence-gathering actions based on the case, every tool proposal passes through enforcement, and prohibited actions are demonstrably blocked before execution.

### Phase E — Bounded repair, safety enforcement and verification

1. Create an isolated worktree or fixture copy.
2. Route patch creation, file access, test execution and replay through registered, permission-checked tools.
3. Make a minimal candidate change only in the authorized worktree.
4. Prove out-of-scope writes, unapproved merges and prohibited commands are blocked before execution.
5. Run a targeted test and replay the same fixture.
6. Show before/after states and report actual test outcomes.

**Done when:** one real fault case is fixed and reproduced passing, with artifacts; safety enforcement tests also prove prohibited actions do not execute. Expand to three cases next.

### Phase F — Three cases, full rehearsal

1. Validate three reproducible fault scenarios.
2. Ensure each has baseline trace, expected failure, investigation, patch and passing test.
3. Run the prediction dataset evaluation separately.
4. Record a backup demo of the known-working commit.
5. Freeze code before presentation and report unfinished areas honestly.

---

## 20. Team responsibilities

Use role labels in prompts and replace them with actual assignments as the team agrees. Avoid duplicate ownership of the same module.

### Member 1 — Agent, trace analysis, and repair

- Local agent under test and LangGraph orchestration.
- Trace/event schema and collection.
- First-deviation analysis and evidence references.
- Investigation tools and budgets.
- Bounded patch workflow, tests and replay.

### Member 2 — Dashboard and graph visualization

- Streamlit application and navigation.
- Execution timeline and event detail views.
- NetworkX/Plotly impact graph.
- Prediction/incident panel.
- Patch diff, test report, before/after presentation.

### Member 3 — Incident data, prediction and evaluation

- Incident schema and persistence.
- Failure-category taxonomy and data-quality rules.
- Feature extraction, baseline model training and prediction outputs.
- Retrieval of similar incidents.
- Dataset splits, model evaluation and result artifacts.
- Reproducible cases, README and demo script.

### Shared responsibility

All members must understand the end-to-end workflow, review claims, run the app, inspect the actual outputs, and avoid saying a feature works before it has been tested.

---

## 21. Final demo script (approximately 3 minutes)

### 0:00–0:20 — The problem

“Multi-step AI agents can produce the wrong final result because of an earlier decision or state update. A log may show what happened, but the developer still needs to investigate where execution first diverged, why, and what later steps were affected.”

### 0:20–0:45 — Show the failed execution

Run one controlled agent task. Show the expected outcome, actual output, event timeline, and the first known deviation.

### 0:45–1:15 — Show prediction and incident learning

Show the predicted failure category, score semantics, model/dataset version, and a relevant verified prior incident. Explain which trace features or matched attributes supported the suggestion. Make clear that it is a prediction, not yet the verified diagnosis.

### 1:15–1:45 — Explain the deviation and impact

Open the event evidence, source/test location, and dependency graph. Show the faulty step and downstream actions that consumed its output/state. Distinguish confirmed dependencies from inferred hypotheses.

### 1:45–2:20 — Correct and verify

Show the candidate diff, run the regression test, replay the same controlled scenario, and compare actual before/after results.

### 2:20–2:45 — Show learning

Finalize the reviewed incident record, show training eligibility/dataset version, and demonstrate the prediction evaluation or a controlled example of a model trained from labelled incidents. Do not claim online learning if the model is not retrained.

### 2:45–3:00 — State measured results and limitations

Report only results generated by the actual test/evaluation scripts. Mention dataset size, synthetic examples, and any unverified capabilities.

---

## 22. Acceptance checklist

### Product identity

- [ ] The README calls Bifura an autonomous, incident-informed causal-debugging agent.
- [ ] The main user question is where and why execution deviated from expected behavior.
- [ ] Safety checks are described as guardrails, not the main product.

### Trace diagnosis

- [ ] A real local run can be captured and normalized.
- [ ] Expected behavior is defined by an assertion/reference criterion.
- [ ] The system finds or reports the earliest evidence-supported deviation.
- [ ] Root-cause hypotheses contain evidence references and uncertainty.
- [ ] The dependency graph distinguishes explicit from inferred relationships.

### Incident learning and prediction

- [ ] Incidents are structured and linked to trace evidence, fixes and tests.
- [ ] The failure taxonomy and labels are documented.
- [ ] The system predicts likely failure category/root cause from trace/incident features or clearly labels a fallback baseline.
- [ ] Prediction results show model/data version and score meaning.
- [ ] Similar incidents can be retrieved and the match explained.
- [ ] Verified versus provisional labels are distinguished.
- [ ] Training/validation/test records are separated and data leakage is checked.
- [ ] Model results are measured against a baseline; no invented scores are presented.
- [ ] A verified incident can be added to a new dataset version and used in a controlled retraining/evaluation cycle, if this stage is claimed as implemented.

### Safety enforcement (required supporting feature)

- [ ] A real central safety policy function returns `ALLOW`, `REVIEW`, or `BLOCK` with reasons.
- [ ] Every proposed tool action is intercepted before execution.
- [ ] Unregistered tools and prohibited commands are blocked.
- [ ] Path traversal, out-of-workspace access, protected-file access and unauthorized writes are blocked.
- [ ] `REVIEW` actions remain unexecuted until authorized human resolution.
- [ ] The executor rejects any proposal without a current, matching `ALLOW` decision.
- [ ] The LLM, prediction model and incident memory cannot override mandatory rules.
- [ ] Logs record the decision, reason, rule and actual execution status without leaking secrets.
- [ ] Automated tests prove blocked actions never reach the executor, including through the public agent path.
- [ ] Dashboard includes a tool-execution/safety-decision view.

### Repair and verification

- [ ] A bounded patch is made in an isolated workspace.
- [ ] The original failure is reproducible.
- [ ] A relevant test fails before the correction where expected.
- [ ] The corrected test passes.
- [ ] Replay uses controlled inputs/fixtures and shows the actual result.
- [ ] Three reproducible failure cases are fixed and regression-tested, or any unfinished cases are explicitly disclosed.

### Dashboard and reproducibility

- [ ] The dashboard shows real run/incident/prediction/graph/test data.
- [ ] It clearly separates prediction, hypothesis, verified cause and verified fix.
- [ ] Working startup commands and dependencies are documented.
- [ ] A known-working commit and backup demo are available.

---

## 23. Rules for any AI coding assistant working on Bifura

Paste or attach this entire file as the primary project context before asking for code. The assistant must follow these rules:

1. **Do not reinterpret the project.** Bifura is an autonomous, incident-informed debugging agent. The primary workflow is deviation detection, evidence-backed root-cause investigation, impact tracing, bounded repair, replay, and learning/prediction from verified incidents.
2. **Do not convert it into Agent Autopsy.** Safety is not Bifura's primary product identity; nevertheless, the safety enforcement engine is a mandatory, implemented feature. It must intercept every tool proposal, enforce `ALLOW`/`REVIEW`/`BLOCK`, block prohibited actions before execution, log decisions, expose them in the dashboard, and pass integration tests proving no bypass. Never omit it or substitute generic sandbox language for working code.
3. **Keep incident-driven prediction central.** The data schema, trained baseline model or explicitly labelled fallback, retrieved incident explanations, prediction UI and evaluation must remain part of the architecture. Do not reduce incident memory to a passive list of historical errors.
4. **Distinguish memory from model training.** Storing/retrieving incidents is not training. State exactly whether code retrieves incidents, updates rules, trains a classical ML model, or fine-tunes an LLM.
5. **No unsupported novelty claims.** Similar tools already provide tracing, evaluation, diagnosis, fix suggestions, datasets, or replay. Emphasize the specific integrated workflow and measured results.
6. **No fabricated results.** Never claim a bug exists upstream until it is reproduced. Never say a fix passed without executing tests. Never fill dashboard charts with invented success data.
7. **Evidence before causal claims.** Temporal ordering alone does not prove causality. Link hypotheses to trace/state/code/test evidence and label uncertainty.
8. **Preserve data integrity.** Mark synthetic examples, retain label history, version datasets/models, and avoid evaluation leakage.
9. **Keep changes bounded.** Work on the requested module, preserve the agreed stack and API/schema contracts, run relevant tests, and report exact files changed and actual results.
10. **Don't overbuild.** Implement the smallest working end-to-end slice first. Add advanced features only after trace → prediction/investigation → impact graph → patch → replay is working.
11. **Respect the stack.** Default to Python, LangGraph, Streamlit, NetworkX, Plotly, Pydantic, pytest and local JSON/SQLite. Do not silently introduce React/FastAPI from another project.
12. **Return implementation evidence.** After each task, report what changed, commands/tests run, results, unresolved issues, and the next concrete step.

### Reusable instruction prompt

> Read `BIFURA_MASTER_PROJECT_SPEC.md` fully before changing code. Summarize the project in your own words, identify the module/task assigned, and state how it supports Bifura's main workflow. Bifura is an incident-informed autonomous causal-debugging agent: it captures failed executions, compares actual and expected behavior, finds the earliest evidence-supported deviation, predicts likely failure categories from labelled incident data, retrieves related verified incidents, investigates root causes, traces downstream dependencies, proposes a bounded patch, and verifies it with replay and regression tests. Incident training/prediction is a core feature. The safety enforcement engine is also mandatory, but secondary to the debugging/learning purpose: every tool proposal must be intercepted and evaluated as ALLOW/REVIEW/BLOCK, prohibited actions must be blocked before execution, and tests must prove that the executor is not reached. Do not replace working enforcement with generic guardrail language. Do not invent APIs or results; inspect the repository first, make a focused change, run appropriate tests, and report actual outputs and remaining limitations.

---

## 24. Open decisions that must be explicit

The team should settle these decisions in the repository rather than allowing individual AI assistants to guess:

- exact LLM provider/model;
- selected local agent/repository under test;
- the three confirmed reproducible fault scenarios;
- exact failure-category taxonomy;
- available amount and provenance of labelled incident data;
- chosen prediction baseline after examining the dataset;
- whether partial-run prediction is implemented in the hackathon prototype or retained as a planned stage;
- criteria for marking a root cause verified and an incident training-eligible; and
- final demo metrics based on actual measurements.

Until a decision is made, document it as **TBD** or **proposed**. Do not silently represent it as finalized.

---

## 25. References for the existing-solution review

These official sources support the competitive context and should be rechecked if the proposal is updated:

1. LangChain, **Introducing LangSmith Engine** (May 13, 2026): https://www.langchain.com/blog/introducing-langsmith-engine
2. LangChain, **How We Built LangSmith Engine: Our Agent for Improving Agents** (May 19, 2026): https://www.langchain.com/blog/how-we-built-langsmith-engine-our-agent-for-improving-agents
3. LangChain, **LangSmith Engine v2: Red teaming and automated testing** (September 24, 2026): https://www.langchain.com/blog/langsmith-engine-v2-redteam
4. LangChain documentation, **LangSmith Studio**: https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/studio.mdx
5. Arize AI, **Phoenix repository**: https://github.com/Arize-ai/phoenix/
6. Arize AI, **Phoenix product site**: https://arize.com/phoenix/
7. Chidori documentation, **Replay & Resume**: https://github.com/ThousandBirdsInc/chidori/blob/main/docs/replay.md

These sources establish that related functions exist; they do not establish a complete feature-by-feature benchmark. Avoid claiming Bifura is unique without further validation.

---

## Final definition

**Bifura is an incident-informed, predictive debugging agent for multi-step AI agents. It learns from structured and verified incident data to predict likely failure patterns, investigates where execution first deviated from expected behavior, explains the evidence and downstream consequences, proposes a bounded correction, and verifies that correction through controlled replay and regression testing.**

Everything built for Bifura should support this workflow. The safety enforcement engine is a required supporting subsystem: it protects the investigation, test and repair tools by enforcing permissions before execution, blocking prohibited actions, requiring review for ambiguous operations, and logging actual outcomes. Its implementation and tests are mandatory, but the project's central value remains incident-informed prediction and evidence-backed debugging—not safety checking alone.
