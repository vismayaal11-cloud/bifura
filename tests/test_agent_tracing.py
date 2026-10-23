"""Tests for Bifura execution trace recording."""

from datetime import datetime, timezone
import pytest

from bifura.schemas.models import (
    ActorType,
    EventType,
    ExecutionStatus,
    SafetyDecisionRecord,
    SafetyDecisionType,
    ToolCallProposal,
    ToolExecutionResult,
)
from bifura.tracing.recorder import TraceRecorder


def test_trace_recorder_successful_tool_flow():
    """Test trace recording sequence for a successful tool execution."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    recorder = TraceRecorder(run_id="run-trace-001", clock=lambda: fixed_time)

    # 1. Task started
    recorder.record_task_started("Read and calculate", "success")

    # 2. Tool proposed
    proposal = ToolCallProposal(
        proposal_id="prop-001",
        tool_name="calculate",
        run_id="run-trace-001",
        arguments={"expression": "15 * 4"},
    )
    recorder.record_tool_proposed(proposal)

    # 3. Safety decision
    decision = SafetyDecisionRecord(
        decision_id="dec-001",
        decision=SafetyDecisionType.ALLOW,
        proposal_id=proposal.proposal_id,
        reason="Allowed by policy",
    )
    recorder.record_safety_decision(decision, proposal)

    # 4. Tool started
    recorder.record_tool_started(proposal)

    # 5. Tool completed
    result = ToolExecutionResult(
        proposal_id=proposal.proposal_id,
        decision_id=decision.decision_id,
        executed=True,
        success=True,
        result_data={"expression": "15 * 4", "result": 60.0},
    )
    recorder.record_tool_completed(proposal, result)

    # 6. Run finished
    recorder.record_run_finished("succeeded", "Completed task successfully.")

    events = recorder.get_events()
    assert len(events) == 6

    # Verify monotonic sequence numbers
    for i, ev in enumerate(events):
        assert ev.sequence == i
        assert ev.timestamp == fixed_time
        assert ev.run_id == "run-trace-001"

    # Verify tool actor is "tool"
    started_ev = events[3]
    assert started_ev.event_type == EventType.TOOL_STARTED.value
    assert started_ev.actor == ActorType.TOOL.value

    completed_ev = events[4]
    assert completed_ev.event_type == EventType.TOOL_COMPLETED.value
    assert completed_ev.actor == ActorType.TOOL.value
    assert completed_ev.output_data == {"expression": "15 * 4", "result": 60.0}


def test_trace_recorder_blocked_tool_flow():
    """Test that a denied tool action emits tool_blocked and never tool_completed."""
    recorder = TraceRecorder(run_id="run-trace-002")

    proposal = ToolCallProposal(
        proposal_id="prop-002",
        tool_name="read_file",
        run_id="run-trace-002",
        arguments={"path": "../../etc/passwd"},
    )
    recorder.record_tool_proposed(proposal)

    decision = SafetyDecisionRecord(
        decision_id="dec-002",
        decision=SafetyDecisionType.BLOCK,
        proposal_id=proposal.proposal_id,
        policy_rule="path_traversal",
        reason="Relative traversal blocked.",
        execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
    )
    recorder.record_safety_decision(decision, proposal)
    recorder.record_tool_blocked(decision, proposal)

    events = recorder.get_events()
    event_types = [e.event_type for e in events]

    assert EventType.TOOL_BLOCKED.value in event_types
    assert EventType.TOOL_STARTED.value not in event_types
    assert EventType.TOOL_COMPLETED.value not in event_types


def test_trace_recorder_failed_tool_flow():
    """Test that a tool runtime error records an error event with error details."""
    recorder = TraceRecorder(run_id="run-trace-003")

    proposal = ToolCallProposal(
        proposal_id="prop-003",
        tool_name="read_file",
        run_id="run-trace-003",
        arguments={"path": "fixtures/missing.txt"},
    )
    recorder.record_tool_started(proposal)

    result = ToolExecutionResult(
        proposal_id=proposal.proposal_id,
        decision_id="dec-003",
        executed=True,
        success=False,
        error_type="FileNotFoundError",
        error_message="File missing.txt not found",
    )
    recorder.record_error(proposal, result)

    events = recorder.get_events()
    error_event = events[-1]
    assert error_event.event_type == EventType.ERROR.value
    assert error_event.actor == ActorType.TOOL.value
    assert error_event.error_type == "FileNotFoundError"
    assert "File missing.txt not found" in error_event.error


def test_trace_recorder_id_generator_injection():
    """Test injecting a custom ID generator."""
    ids = ["ev-custom-1", "ev-custom-2", "ev-custom-3"]
    it = iter(ids)

    recorder = TraceRecorder(
        run_id="run-trace-004",
        id_generator=lambda: next(it),
    )

    recorder.record_task_started("Test task", "success")
    recorder.record_run_finished("succeeded", "Done")

    events = recorder.get_events()
    assert events[0].event_id == "ev-custom-1"
    assert events[1].event_id == "ev-custom-2"
