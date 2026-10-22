"""Unit tests for Bifura's reconciled canonical contracts."""

import pytest
from pydantic import ValidationError

# Verify imports work from both canonical bifura.schemas.models and bifura.contracts
from bifura.contracts import (
    DecisionType,
    DependencyEdge,
    DeviationRecord,
    DeviationResult,
    ExecutionStatus,
    FailureCategory,
    ImpactGraph,
    IncidentRecord,
    PredictionResult,
    SafetyDecision,
    SafetyDecisionRecord,
    SafetyDecisionType,
    ToolCallProposal,
    ToolProposal,
    TraceEvent,
    VerificationReport,
)
import bifura.schemas.models as canonical_models


# ---------------------------------------------------------------------------
# Original Baseline Tests (Preserved)
# ---------------------------------------------------------------------------


def test_trace_event_accepts_valid_data():
    event = TraceEvent(
        run_id="run-001",
        event_id="event-001",
        sequence=0,
        event_type="tool_call",
        tool_name="read_fixture",
    )

    assert event.run_id == "run-001"
    assert event.sequence == 0


def test_trace_event_rejects_negative_sequence():
    with pytest.raises(ValidationError):
        TraceEvent(
            run_id="run-001",
            event_id="event-002",
            sequence=-1,
            event_type="tool_call",
        )


def test_contract_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        TraceEvent(
            run_id="run-001",
            event_id="event-003",
            sequence=0,
            event_type="tool_call",
            unexpected_field="not allowed",
        )


def test_tool_proposal_accepts_structured_arguments():
    proposal = ToolProposal(
        proposal_id="proposal-001",
        tool_name="read_fixture",
        arguments={"path": "fixtures/example.json"},
        purpose="Inspect a local test fixture",
        run_id="run-001",
    )

    assert proposal.arguments["path"] == "fixtures/example.json"


def test_safety_decision_supports_block():
    decision = SafetyDecision(
        decision_id="decision-001",
        proposal_id="proposal-001",
        decision=DecisionType.BLOCK,
        policy_rule="POLICY-TEST-001",
        reason="This action is prohibited in the test.",
    )

    assert decision.decision == DecisionType.BLOCK


# ---------------------------------------------------------------------------
# Reconciled Contract Tests
# ---------------------------------------------------------------------------


def test_schema_version_defaults_and_serializes():
    event = TraceEvent(
        run_id="run-001",
        event_id="event-001",
        sequence=1,
        event_type="tool_proposed",
    )
    assert event.schema_version == "1.0"
    data = event.model_dump()
    assert data["schema_version"] == "1.0"

    # Accepting incoming data with schema_version
    parsed = TraceEvent.model_validate(data)
    assert parsed.schema_version == "1.0"


def test_import_equivalence_between_schemas_and_contracts():
    assert canonical_models.TraceEvent is TraceEvent
    assert canonical_models.ToolCallProposal is ToolCallProposal
    assert canonical_models.ToolProposal is ToolProposal
    assert canonical_models.SafetyDecisionRecord is SafetyDecisionRecord
    assert canonical_models.SafetyDecision is SafetyDecision


def test_trace_event_supports_structured_data_and_references():
    event = TraceEvent(
        run_id="run-001",
        event_id="event-010",
        sequence=2,
        event_type="tool_completed",
        actor="tool",
        tool_call_id="call-001",
        input_data={"param": 42},
        output_data={"result": "ok"},
        input_ref="data/fixtures/input.json",
        provenance="tool_output",
        depends_on_event_ids=["event-009"],
    )
    assert event.actor == "tool"
    assert event.input_data == {"param": 42}
    assert event.output_data == {"result": "ok"}
    assert event.depends_on_event_ids == ["event-009"]


def test_safety_decision_record_and_execution_status():
    record = SafetyDecisionRecord(
        decision_id="decision-002",
        proposal_id="proposal-002",
        tool_call_id="call-002",
        decision=SafetyDecisionType.BLOCK,
        rule_ids=["workspace_scope", "no_shell"],
        reason="Execution of shell command is prohibited.",
        execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
    )
    assert record.decision == DecisionType.BLOCK
    assert record.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION
    assert "workspace_scope" in record.rule_ids


def test_failure_category_canonical_taxonomy_and_aliases():
    # Canonical 7 categories
    assert (
        FailureCategory.TOOL_INPUT_VALIDATION.value == "tool_input_validation"
    )
    assert FailureCategory.STATE_OR_DATAFLOW.value == "state_or_dataflow"
    assert (
        FailureCategory.PLANNING_OR_TOOL_SEQUENCE.value
        == "planning_or_tool_sequence"
    )
    assert FailureCategory.RETRY_LOGIC.value == "retry_logic"
    assert (
        FailureCategory.EXTERNAL_TOOL_OR_ENVIRONMENT.value
        == "external_tool_or_environment"
    )
    assert (
        FailureCategory.MODEL_REASONING_OR_INSTRUCTION_HANDLING.value
        == "model_reasoning_or_instruction_handling"
    )
    assert (
        FailureCategory.UNKNOWN_INSUFFICIENT_EVIDENCE.value
        == "unknown_insufficient_evidence"
    )

    # Aliases
    assert FailureCategory.STATE_PROPAGATION.value == "state_or_dataflow"
    assert (
        FailureCategory.PLAN_TOOL_SEQUENCE.value == "planning_or_tool_sequence"
    )


def test_impact_graph_and_dependency_edge():
    edge = DependencyEdge(
        from_event_id="ev-1",
        to_event_id="ev-2",
        dependency_type="consumes_output",
        explanation="Event 2 consumed the structured output from Event 1",
    )
    graph = ImpactGraph(run_id="run-001", edges=[edge])
    assert len(graph.edges) == 1
    assert graph.edges[0].from_event_id == "ev-1"


def test_deviation_record_and_aliases():
    record = DeviationRecord(
        run_id="run-001",
        first_deviation_event_id="ev-3",
        expected_behavior="Valid JSON object returned",
        observed_behavior="None / Null returned",
        description="Tool output schema mismatch",
    )
    assert record.found is True
    assert record.first_deviation_event_id == "ev-3"
    assert DeviationResult is DeviationRecord


def test_verification_report():
    report = VerificationReport(
        verification_id="ver-001",
        run_id="run-001",
        patch_id="patch-001",
        passed=True,
        targeted_test_status="passed",
        regression_test_status="passed",
        replay_status="passed",
        summary="Targeted fix succeeded and replay passed.",
    )
    assert report.passed is True
    assert report.replay_status == "passed"
