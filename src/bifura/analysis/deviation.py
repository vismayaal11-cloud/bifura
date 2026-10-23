"""First-deviation detection for Bifura execution traces.

Compares observed trace events against expected action sequences to identify
the earliest deviation (safety block, invariant failure, out-of-order, or unexpected action).
"""

from __future__ import annotations

from typing import Any

from bifura.schemas.models import DeviationRecord, EventType, TraceEvent


def detect_first_deviation(
    run_id: str,
    events: list[TraceEvent],
    expected_action_sequence: list[str],
) -> DeviationRecord:
    """Detect the first discrepancy between expected sequence and observed events.

    Args:
        run_id: Identifier of the run.
        events: Chronological list of recorded TraceEvents.
        expected_action_sequence: Expected tool action sequence (e.g. ["read_file", "calculate", "write_file"]).

    Returns:
        A canonical DeviationRecord. If no deviation was found, returns found=False.
    """
    sorted_events = sorted(events, key=lambda e: e.sequence)

    # Track actual proposed tool order
    tool_sequence_index = 0
    actual_tools: list[str] = []

    for ev in sorted_events:
        # 1. Assertion / invariant failure
        if ev.event_type == EventType.ASSERTION_FAILED.value:
            expected_data = ev.input_data.get("expected") if ev.input_data else None
            actual_data = ev.input_data.get("actual") if ev.input_data else None
            return DeviationRecord(
                run_id=run_id,
                deviation_id=f"dev-{ev.event_id}",
                event_id=ev.event_id,
                first_deviation_event_id=ev.event_id,
                found=True,
                expected={"expected": expected_data} if expected_data else None,
                actual={"actual": actual_data} if actual_data else None,
                expected_behavior="Invariant check passes without discrepancy.",
                observed_behavior=ev.summary or "Invariant failure detected.",
                description=ev.summary or "Invariant assertion failure.",
                first_observed_deviation=True,
                evidence_refs=[ev.event_id],
                status="observed",
            )

        # 2. Tool blocked by safety policy
        if ev.event_type == EventType.TOOL_BLOCKED.value:
            return DeviationRecord(
                run_id=run_id,
                deviation_id=f"dev-{ev.event_id}",
                event_id=ev.event_id,
                first_deviation_event_id=ev.event_id,
                found=True,
                expected={"action": expected_action_sequence[tool_sequence_index] if tool_sequence_index < len(expected_action_sequence) else None},
                actual={"blocked_tool": ev.tool_name, "error": ev.error},
                expected_behavior="Authorized tool action inside sandbox.",
                observed_behavior=f"Tool '{ev.tool_name}' blocked by safety policy: {ev.error}",
                description=ev.summary or "Action blocked by safety policy.",
                first_observed_deviation=True,
                evidence_refs=[ev.event_id],
                status="observed",
            )

        # 3. Tool runtime error during execution
        if ev.event_type == EventType.ERROR.value:
            return DeviationRecord(
                run_id=run_id,
                deviation_id=f"dev-{ev.event_id}",
                event_id=ev.event_id,
                first_deviation_event_id=ev.event_id,
                found=True,
                expected={"tool_execution": "success"},
                actual={"error_type": ev.error_type, "error_message": ev.error},
                expected_behavior="Tool completes execution without error.",
                observed_behavior=f"Tool failed with {ev.error_type}: {ev.error}",
                description=ev.summary or f"Tool runtime error: {ev.error}",
                first_observed_deviation=True,
                evidence_refs=[ev.event_id],
                status="observed",
            )

        # 4. Check sequence alignment on tool_proposed or tool_started
        if ev.event_type == EventType.TOOL_PROPOSED.value and ev.tool_name:
            actual_tools.append(ev.tool_name)
            if tool_sequence_index < len(expected_action_sequence):
                expected_tool = expected_action_sequence[tool_sequence_index]
                if ev.tool_name != expected_tool:
                    return DeviationRecord(
                        run_id=run_id,
                        deviation_id=f"dev-{ev.event_id}",
                        event_id=ev.event_id,
                        first_deviation_event_id=ev.event_id,
                        found=True,
                        expected={"expected_tool": expected_tool, "step": tool_sequence_index},
                        actual={"actual_tool": ev.tool_name, "step": tool_sequence_index},
                        expected_behavior=f"Expected tool '{expected_tool}' at step {tool_sequence_index}.",
                        observed_behavior=f"Proposed out-of-order tool '{ev.tool_name}'.",
                        description=f"Action sequence mismatch: expected '{expected_tool}', found '{ev.tool_name}'.",
                        first_observed_deviation=True,
                        evidence_refs=[ev.event_id],
                        status="observed",
                    )
            else:
                # Unexpected additional action beyond expected sequence
                return DeviationRecord(
                    run_id=run_id,
                    deviation_id=f"dev-{ev.event_id}",
                    event_id=ev.event_id,
                    first_deviation_event_id=ev.event_id,
                    found=True,
                    expected={"expected_actions_count": len(expected_action_sequence)},
                    actual={"extra_tool": ev.tool_name},
                    expected_behavior="Workflow completed according to plan.",
                    observed_behavior=f"Unexpected additional tool '{ev.tool_name}'.",
                    description=f"Unexpected action '{ev.tool_name}' beyond expected sequence.",
                    first_observed_deviation=True,
                    evidence_refs=[ev.event_id],
                    status="observed",
                )

            tool_sequence_index += 1

    # 5. Check if incomplete (fewer actions executed than expected)
    if tool_sequence_index < len(expected_action_sequence):
        last_ev_id = sorted_events[-1].event_id if sorted_events else "ev-000"
        missing_tool = expected_action_sequence[tool_sequence_index]
        return DeviationRecord(
            run_id=run_id,
            deviation_id=f"dev-missing-{run_id}",
            event_id=last_ev_id,
            first_deviation_event_id=last_ev_id,
            found=True,
            expected={"expected_actions": expected_action_sequence},
            actual={"executed_actions": actual_tools},
            expected_behavior="All expected actions completed.",
            observed_behavior=f"Run ended before executing '{missing_tool}'.",
            description=f"Missing expected action '{missing_tool}'.",
            first_observed_deviation=True,
            evidence_refs=[last_ev_id],
            status="observed",
        )

    # 6. Success: No deviation found
    return DeviationRecord(
        run_id=run_id,
        deviation_id=f"dev-none-{run_id}",
        event_id=None,
        first_deviation_event_id=None,
        found=False,
        expected={"expected_actions": expected_action_sequence},
        actual={"executed_actions": actual_tools},
        expected_behavior="Execution strictly conforms to expected sequence.",
        observed_behavior="Execution completed successfully with zero deviations.",
        description="No deviation detected; execution matched expected sequence.",
        first_observed_deviation=False,
        evidence_refs=[],
        status="observed",
    )
