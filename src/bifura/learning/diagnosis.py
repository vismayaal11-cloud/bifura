"""Diagnosis module for Bifura run bundles.

Analyzes trace events, safety decisions, tool proposals, execution results, and deviations
to diagnose canonical FailureCategories backed strictly by observable evidence.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    EventType,
    FailureCategory,
    IncidentRecord,
    LabelStatus,
    SafetyDecisionType,
    utc_now,
)


def diagnose_run_bundle(
    bundle: RunBundle,
    id_generator: Callable[[], str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> IncidentRecord | None:
    """Diagnose a FailureCategory from the complete evidence in a RunBundle.

    Returns None if no deviation was found (successful run).
    Assigns a canonical FailureCategory only when justified by trace and bundle evidence.
    Returns UNKNOWN_INSUFFICIENT_EVIDENCE if deviation exists but evidence is inconclusive.
    """
    deviation = bundle.deviation
    if deviation is None or not deviation.found:
        return None

    # Gather evidence signals across the entire bundle
    dev_desc = (deviation.description or "").lower()
    dev_expected = (deviation.expected_behavior or "").lower()
    dev_observed = (deviation.observed_behavior or "").lower()
    dev_explanation = (deviation.explanation or "").lower()
    exec_summary = (bundle.actual_execution_summary or "").lower()

    combined_dev_text = f"{dev_desc} {dev_expected} {dev_observed} {dev_explanation} {exec_summary}"

    # Trace events and safety decisions
    events = bundle.events or []
    decisions = bundle.safety_decisions or []
    results = bundle.execution_results or []

    blocked_decisions = [
        d for d in decisions if d.decision == SafetyDecisionType.BLOCK
    ]
    assertion_failed_events = [
        e for e in events if e.event_type == EventType.ASSERTION_FAILED.value
    ]
    error_events = [
        e for e in events if e.event_type == EventType.ERROR.value
    ]
    tool_proposals = [
        e for e in events if e.event_type == EventType.TOOL_PROPOSED.value
    ]

    # Collect evidence references
    evidence_refs: list[str] = list(deviation.evidence_refs or [])
    affected_event_ids: list[str] = []

    if deviation.first_deviation_event_id:
        if deviation.first_deviation_event_id not in evidence_refs:
            evidence_refs.append(deviation.first_deviation_event_id)
        affected_event_ids.append(deviation.first_deviation_event_id)

    for d in blocked_decisions:
        if d.decision_id not in evidence_refs:
            evidence_refs.append(d.decision_id)
        if d.evidence_refs:
            for ref in d.evidence_refs:
                if ref not in evidence_refs:
                    evidence_refs.append(ref)

    for e in assertion_failed_events + error_events:
        if e.event_id not in evidence_refs:
            evidence_refs.append(e.event_id)
        if e.event_id not in affected_event_ids:
            affected_event_ids.append(e.event_id)

    # -------------------------------------------------------------------------
    # Evidence Evaluation & Taxonomy Matching
    # -------------------------------------------------------------------------
    diagnosed_category: FailureCategory
    observed_pattern: str
    root_cause_summary: str
    hypotheses: list[str]

    # Signal 1: TOOL_INPUT_VALIDATION
    # Checks for path traversal, escaping sandbox/workspace, invalid arguments,
    # or safety engine blocks on input containment.
    is_path_traversal = any(
        ".." in str(p.input_data or {}) or "../" in str(p.input_data or {})
        for p in tool_proposals
    ) or any(
        "containment" in (d.policy_rule or "").lower()
        or "traversal" in (d.reason or "").lower()
        or "escapes" in (d.reason or "").lower()
        for d in blocked_decisions
    ) or "traversal" in combined_dev_text or "escape" in combined_dev_text

    is_invalid_argument = any(
        "argument" in combined_dev_text
        or "invalid input" in combined_dev_text
        or "validation" in (d.policy_rule or "").lower()
        for d in blocked_decisions
    ) or any(
        "validation" in (r.error_type or "").lower()
        or "valueerror" in (r.error_type or "").lower()
        for r in results
    )

    # Signal 2: STATE_OR_DATAFLOW
    # Checks for state mismatch, discrepancy between expected output of previous step
    # and actual input of subsequent step, stale cached calculation inputs.
    is_stale_or_dataflow = any(
        "stale" in combined_dev_text
        or "cache" in combined_dev_text
        or "dataflow" in combined_dev_text
        or "state mismatch" in combined_dev_text
        or (deviation.expected is not None and deviation.actual is not None)
        for _ in [1]
    ) or any(
        "stale" in (e.summary or "").lower()
        or "mismatch" in (e.error or "").lower()
        or "state" in (e.summary or "").lower()
        for e in assertion_failed_events
    )

    # Signal 3: PLANNING_OR_TOOL_SEQUENCE
    # Checks for out-of-order execution, e.g. tool executed before required precursor
    # in expected_action_sequence, or assertion failed on sequence precondition.
    actual_tool_sequence = [
        e.tool_name for e in tool_proposals if e.tool_name is not None
    ]
    expected_sequence = bundle.expected_action_sequence or []
    is_out_of_sequence = False

    if expected_sequence and actual_tool_sequence:
        # Check if an action appears before its expected prerequisite
        for i, tool in enumerate(actual_tool_sequence):
            if tool in expected_sequence:
                expected_idx = expected_sequence.index(tool)
                # Check if preceding expected tools were missed
                for prereq in expected_sequence[:expected_idx]:
                    if prereq not in actual_tool_sequence[:i]:
                        is_out_of_sequence = True
                        break
            if is_out_of_sequence:
                break

    is_sequence_violation = (
        is_out_of_sequence
        or "sequence" in combined_dev_text
        or "order" in combined_dev_text
        or "precondition" in combined_dev_text
        or any(
            "sequence" in (e.summary or "").lower()
            or "order" in (e.summary or "").lower()
            for e in assertion_failed_events
        )
    )

    # Signal 4: RETRY_LOGIC
    is_retry_failure = (
        "retry" in combined_dev_text
        or "loop" in combined_dev_text
        or (len(tool_proposals) >= 3 and len({p.tool_name for p in tool_proposals}) == 1 and bool(error_events))
    )

    # Signal 5: EXTERNAL_TOOL_OR_ENVIRONMENT
    is_environment_failure = (
        "environment" in combined_dev_text
        or "oserror" in combined_dev_text
        or "connection" in combined_dev_text
        or any(
            "oserror" in (r.error_type or "").lower()
            or "filenotfound" in (r.error_type or "").lower()
            for r in results
        )
    )

    # Signal 6: MODEL_REASONING_OR_INSTRUCTION_HANDLING
    is_reasoning_failure = (
        "reasoning" in combined_dev_text
        or "instruction" in combined_dev_text
        or "hallucination" in combined_dev_text
    )

    # -------------------------------------------------------------------------
    # Decision Matrix based strictly on verified evidence
    # -------------------------------------------------------------------------
    if (is_path_traversal or is_invalid_argument) and (blocked_decisions or "path" in combined_dev_text):
        diagnosed_category = FailureCategory.TOOL_INPUT_VALIDATION
        observed_pattern = "path_traversal_blocked" if is_path_traversal else "invalid_tool_input"
        root_cause_summary = (
            "Tool proposal contained invalid inputs or path traversal outside authorized containment; "
            f"blocked by safety policy rule '{blocked_decisions[0].policy_rule if blocked_decisions else 'containment'}'."
        )
        hypotheses = [
            "Agent attempted relative path traversal escaping authorized root directory.",
            "Agent input parameters failed boundary validation.",
        ]

    elif is_sequence_violation and not is_stale_or_dataflow:
        diagnosed_category = FailureCategory.PLANNING_OR_TOOL_SEQUENCE
        observed_pattern = "out_of_order_tool_execution"
        root_cause_summary = (
            f"Agent proposed actions in an out-of-order sequence (actual: {actual_tool_sequence}, "
            f"expected: {expected_sequence}), violating workflow ordering preconditions."
        )
        hypotheses = [
            "Agent planning loop scheduled downstream side-effect before prerequisite computation.",
            "Missing precondition check in agent state machine allowed premature execution.",
        ]

    elif is_stale_or_dataflow:
        diagnosed_category = FailureCategory.STATE_OR_DATAFLOW
        observed_pattern = "stale_state_or_dataflow_mismatch"
        root_cause_summary = (
            "Discrepancy detected between expected dataflow and actual execution input. "
            "Agent used stale or unrefreshed cached values instead of upstream tool outputs."
        )
        hypotheses = [
            "Agent memory referenced cached state instead of freshly updated context.",
            "Dataflow propagation between read_file and downstream calculate failed.",
        ]

    elif is_retry_failure:
        diagnosed_category = FailureCategory.RETRY_LOGIC
        observed_pattern = "unbounded_or_unadapted_retry"
        root_cause_summary = "Agent retried failing operations repeatedly without adapting inputs or applying backoff."
        hypotheses = ["Agent retry loop lacked parameter mutation on recurring failure."]

    elif is_environment_failure:
        diagnosed_category = FailureCategory.EXTERNAL_TOOL_OR_ENVIRONMENT
        observed_pattern = "external_system_environment_error"
        root_cause_summary = "Execution failed due to missing environmental resources or external tool failure."
        hypotheses = ["External filesystem or environment prerequisite was unavailable."]

    elif is_reasoning_failure:
        diagnosed_category = FailureCategory.MODEL_REASONING_OR_INSTRUCTION_HANDLING
        observed_pattern = "instruction_interpretation_failure"
        root_cause_summary = "Agent deviated from explicit prompt instructions during reasoning phase."
        hypotheses = ["Model reasoning misconstrued boundary constraints in user task."]

    else:
        # Honest fallback when evidence is insufficient
        diagnosed_category = FailureCategory.UNKNOWN_INSUFFICIENT_EVIDENCE
        observed_pattern = "unclassified_deviation"
        root_cause_summary = (
            "A deviation was recorded, but available trace events and safety records "
            "do not contain sufficient observable evidence to assign a definitive category."
        )
        hypotheses = ["Insufficient trace evidence to confirm specific root cause."]

    # Generate incident ID
    now = clock() if clock is not None else utc_now()
    if id_generator is not None:
        inc_id = id_generator()
    else:
        inc_id = f"inc-{bundle.run.run_id}"

    first_dev_event = deviation.first_deviation_event_id
    if not first_dev_event and affected_event_ids:
        first_dev_event = affected_event_ids[0]

    return IncidentRecord(
        incident_id=inc_id,
        run_id=bundle.run.run_id,
        source_run_id=bundle.run.run_id,
        task_summary=bundle.run.task_summary or bundle.run.task_text,
        observed_pattern=observed_pattern,
        expected_behavior=deviation.expected_behavior or bundle.run.expected_behavior,
        observed_behavior=deviation.observed_behavior or bundle.actual_execution_summary,
        first_deviation_event_id=first_dev_event,
        failure_category=diagnosed_category,
        label_status=LabelStatus.SUSPECTED,
        root_cause_status="suspected",
        root_cause_summary=root_cause_summary,
        root_cause_hypotheses=hypotheses,
        evidence_refs=evidence_refs,
        affected_event_ids=affected_event_ids,
        data_origin="controlled_fixture" if bundle.run.is_fixture else "run_bundle",
        provenance="controlled_fixture" if bundle.run.is_fixture else bundle.run.agent_name,
        training_eligible=False,  # Enforces honesty rule
        training_eligibility="pending_review",
        review_status="pending",
        replay_status="not_run",
        dataset_version="dataset-v1",
        created_at=now,
    )
