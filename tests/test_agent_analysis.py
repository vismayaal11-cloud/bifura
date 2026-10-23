"""Tests for first-deviation detection and impact graph building."""

from datetime import datetime, timezone
import pytest

from bifura.analysis.deviation import detect_first_deviation
from bifura.analysis.impact import build_impact_graph
from bifura.schemas.models import EventType, TraceEvent


def make_event(
    seq: int,
    event_type: str,
    tool_name: str | None = None,
    error: str | None = None,
    error_type: str | None = None,
    summary: str | None = None,
    depends_on: list[str] | None = None,
) -> TraceEvent:
    """Helper to create a deterministic TraceEvent for analysis testing."""
    return TraceEvent(
        run_id="run-analysis-test",
        event_id=f"ev-{seq:03d}",
        sequence=seq,
        event_type=event_type,
        tool_name=tool_name,
        error=error,
        error_type=error_type,
        summary=summary,
        depends_on_event_ids=depends_on or [],
        timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )


def test_detect_deviation_success():
    """Test that a matching run produces found=False with no deviation."""
    expected = ["read_file", "calculate", "write_file"]
    events = [
        make_event(0, EventType.TASK_STARTED.value),
        make_event(1, EventType.TOOL_PROPOSED.value, tool_name="read_file"),
        make_event(2, EventType.TOOL_COMPLETED.value, tool_name="read_file"),
        make_event(3, EventType.TOOL_PROPOSED.value, tool_name="calculate"),
        make_event(4, EventType.TOOL_COMPLETED.value, tool_name="calculate"),
        make_event(5, EventType.TOOL_PROPOSED.value, tool_name="write_file"),
        make_event(6, EventType.TOOL_COMPLETED.value, tool_name="write_file"),
        make_event(7, EventType.RUN_FINISHED.value),
    ]

    dev = detect_first_deviation("run-analysis-test", events, expected)
    assert dev.found is False
    assert dev.first_deviation_event_id is None
    assert "No deviation detected" in (dev.description or "")


def test_detect_deviation_single_blocked_action():
    """Test that a single blocked action is identified as the first deviation."""
    expected = ["read_file", "calculate", "write_file"]
    events = [
        make_event(0, EventType.TASK_STARTED.value),
        make_event(1, EventType.TOOL_PROPOSED.value, tool_name="read_file"),
        make_event(2, EventType.TOOL_BLOCKED.value, tool_name="read_file", error="Path traversal"),
        make_event(3, EventType.RUN_FINISHED.value),
    ]

    dev = detect_first_deviation("run-analysis-test", events, expected)
    assert dev.found is True
    assert dev.first_deviation_event_id == "ev-002"
    assert "Path traversal" in (dev.observed_behavior or "")


def test_detect_deviation_multiple_deviations_earliest_selected():
    """Test that the earliest deviation is selected when multiple deviations occur."""
    expected = ["read_file", "calculate", "write_file"]
    events = [
        make_event(0, EventType.TASK_STARTED.value),
        # Deviation 1: Out-of-order write_file at sequence 1 (event ev-001)
        make_event(1, EventType.TOOL_PROPOSED.value, tool_name="write_file"),
        make_event(2, EventType.TOOL_COMPLETED.value, tool_name="write_file"),
        # Deviation 2: Assertion failure at sequence 3 (event ev-003)
        make_event(3, EventType.ASSERTION_FAILED.value, summary="Sequence error"),
        # Deviation 3: Error at sequence 4 (event ev-004)
        make_event(4, EventType.ERROR.value, error="Failed"),
    ]

    dev = detect_first_deviation("run-analysis-test", events, expected)
    assert dev.found is True
    # The earliest deviation is ev-001 (unexpected write_file at step 0)
    assert dev.first_deviation_event_id == "ev-001"


def test_detect_deviation_assertion_failure_takes_precedence_when_first():
    """Test that an assertion_failed event is captured as first deviation when it occurs first."""
    expected = ["read_file", "calculate", "write_file"]
    events = [
        make_event(0, EventType.TASK_STARTED.value),
        make_event(1, EventType.TOOL_PROPOSED.value, tool_name="read_file"),
        make_event(2, EventType.TOOL_COMPLETED.value, tool_name="read_file"),
        make_event(3, EventType.ASSERTION_FAILED.value, summary="Discrepancy: stale expression"),
        make_event(4, EventType.TOOL_PROPOSED.value, tool_name="calculate"),
    ]

    dev = detect_first_deviation("run-analysis-test", events, expected)
    assert dev.found is True
    assert dev.first_deviation_event_id == "ev-003"
    assert "Discrepancy: stale expression" in (dev.description or "")


def test_build_impact_graph_with_dependencies():
    """Test that impact graph correctly reflects explicit dependencies."""
    events = [
        make_event(0, EventType.TOOL_COMPLETED.value, tool_name="read_file"),
        make_event(1, EventType.TOOL_COMPLETED.value, tool_name="calculate", depends_on=["ev-000"]),
        make_event(2, EventType.TOOL_COMPLETED.value, tool_name="write_file", depends_on=["ev-001"]),
    ]

    graph = build_impact_graph("run-analysis-test", events)
    assert graph is not None
    assert len(graph.edges) == 2
    assert graph.edges[0].from_event_id == "ev-000"
    assert graph.edges[0].to_event_id == "ev-001"
    assert graph.edges[1].from_event_id == "ev-001"
    assert graph.edges[1].to_event_id == "ev-002"


def test_build_impact_graph_without_dependencies():
    """Test that impact graph returns None when no dependencies exist."""
    events = [
        make_event(0, EventType.TOOL_COMPLETED.value, tool_name="read_file"),
        make_event(1, EventType.TOOL_COMPLETED.value, tool_name="calculate"),
    ]

    graph = build_impact_graph("run-analysis-test", events)
    assert graph is None
