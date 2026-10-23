"""Unit tests for the central tool executor and fail-closed safety enforcement."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from bifura.schemas.models import (
    ExecutionStatus,
    SafetyDecisionRecord,
    SafetyDecisionType,
    ToolCallProposal,
)
from bifura.tools.executor import execute_tool_action


@pytest.fixture
def base_context(tmp_path: Path) -> dict:
    """Provide a standard test context."""
    workspace = tmp_path / "sandbox"
    runtime = workspace / "runtime"
    fixtures = workspace / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)

    (fixtures / "scenario_1.txt").write_text("15 * 4", encoding="utf-8")

    return {
        "mode": "demo",
        "workspace_root": str(workspace),
        "sandbox_root": str(runtime),
        "allowed_tools": ["read_file", "calculate", "write_file"],
        "permissions": {
            "allow_network": False,
            "write_sandbox": True,
            "write_project": False,
        },
        "provenance": "trusted_orchestrator",
    }


def mock_policy_evaluator(
    proposal: ToolCallProposal,
    context: dict,
) -> SafetyDecisionRecord:
    """Mock safety evaluator for testing central executor enforcement."""
    # Harmless default: Allow recognized tools with valid args
    if proposal.tool_name in context.get("allowed_tools", []):
        # Specific test triggers
        if proposal.arguments.get("force_block"):
            return SafetyDecisionRecord(
                decision_id="dec-block-001",
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="test_block_rule",
                reason="Forced block for testing.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
            )
        if proposal.arguments.get("force_review"):
            return SafetyDecisionRecord(
                decision_id="dec-review-001",
                decision=SafetyDecisionType.REVIEW,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="test_review_rule",
                reason="Forced review for testing.",
                execution_status=ExecutionStatus.AWAITING_REVIEW,
            )

        return SafetyDecisionRecord(
            decision_id="dec-allow-001",
            decision=SafetyDecisionType.ALLOW,
            proposal_id=proposal.proposal_id,
            run_id=proposal.run_id,
            policy_rule="allowed_tool_rule",
            reason="Tool is authorized and parameters meet policy.",
            execution_status=ExecutionStatus.NOT_STARTED,
        )

    return SafetyDecisionRecord(
        decision_id="dec-block-unallowed",
        decision=SafetyDecisionType.BLOCK,
        proposal_id=proposal.proposal_id,
        run_id=proposal.run_id,
        policy_rule="disallowed_tool",
        reason=f"Tool '{proposal.tool_name}' not permitted.",
        execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
    )


def test_executor_successful_allow(base_context: dict):
    """Test executing an ALLOW decision for a valid local tool."""
    proposal = ToolCallProposal(
        proposal_id="prop-001",
        tool_name="calculate",
        run_id="run-001",
        arguments={"expression": "15 * 4"},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=mock_policy_evaluator,
    )

    assert decision.decision == SafetyDecisionType.ALLOW
    assert result.executed is True
    assert result.success is True
    assert result.result_data == {"expression": "15 * 4", "result": 60.0}
    assert result.error_type is None


def test_executor_block_decision_prevents_execution(base_context: dict):
    """Test that a BLOCK decision from the evaluator prevents execution."""
    proposal = ToolCallProposal(
        proposal_id="prop-002",
        tool_name="calculate",
        run_id="run-001",
        arguments={"expression": "15 * 4", "force_block": True},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=mock_policy_evaluator,
    )

    assert decision.decision == SafetyDecisionType.BLOCK
    assert result.executed is False
    assert result.success is False
    assert result.result_data is None
    assert result.error_type == "SafetyBlockError"


def test_executor_review_decision_prevents_execution(base_context: dict):
    """Test that a REVIEW decision suspends tool execution."""
    proposal = ToolCallProposal(
        proposal_id="prop-003",
        tool_name="calculate",
        run_id="run-001",
        arguments={"expression": "15 * 4", "force_review": True},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=mock_policy_evaluator,
    )

    assert decision.decision == SafetyDecisionType.REVIEW
    assert result.executed is False
    assert result.success is None
    assert result.result_data is None
    assert result.error_type == "AwaitingReviewError"


def test_executor_missing_evaluator_fails_closed(base_context: dict):
    """Test that omitting the evaluator triggers fail-closed BLOCK behavior."""
    proposal = ToolCallProposal(
        proposal_id="prop-004",
        tool_name="calculate",
        run_id="run-001",
        arguments={"expression": "15 * 4"},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=None,
    )

    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.policy_rule == "fail_closed_guard"
    assert decision.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION
    assert result.executed is False
    assert result.success is False
    assert result.error_type == "SafetyBlockError"


def test_executor_evaluator_exception_fails_closed(base_context: dict):
    """Test that an evaluator raising an unhandled exception triggers fail-closed."""
    def broken_evaluator(prop, ctx):
        raise RuntimeError("Crash inside policy engine!")

    proposal = ToolCallProposal(
        proposal_id="prop-005",
        tool_name="calculate",
        run_id="run-001",
        arguments={"expression": "15 * 4"},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=broken_evaluator,
    )

    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.policy_rule == "fail_closed_guard"
    assert "Crash inside policy engine!" in decision.reason
    assert result.executed is False
    assert result.success is False


def test_executor_invalid_evaluator_return_type_fails_closed(base_context: dict):
    """Test that an evaluator returning something other than SafetyDecisionRecord fails closed."""
    def invalid_evaluator(prop, ctx):
        return {"decision": "ALLOW"}  # Not a SafetyDecisionRecord

    proposal = ToolCallProposal(
        proposal_id="prop-006",
        tool_name="calculate",
        run_id="run-001",
        arguments={"expression": "15 * 4"},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=invalid_evaluator,  # type: ignore
    )

    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.policy_rule == "fail_closed_guard"
    assert result.executed is False


def test_executor_inconsistent_proposal_id_fails_closed(base_context: dict):
    """Test that a decision returning a different proposal_id fails closed."""
    def mismatched_evaluator(prop, ctx):
        return SafetyDecisionRecord(
            decision_id="dec-mismatch",
            decision=SafetyDecisionType.ALLOW,
            proposal_id="totally-different-id",
            reason="Mismatched ID",
        )

    proposal = ToolCallProposal(
        proposal_id="prop-007",
        tool_name="calculate",
        run_id="run-001",
        arguments={"expression": "15 * 4"},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=mismatched_evaluator,
    )

    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.policy_rule == "fail_closed_guard"
    assert "does not match" in decision.reason
    assert result.executed is False


def test_executor_unregistered_tool_fails_closed(base_context: dict):
    """Test that an unregistered tool is not executed even if evaluator says ALLOW."""
    def allow_anything_evaluator(prop, ctx):
        return SafetyDecisionRecord(
            decision_id="dec-allow-evil",
            decision=SafetyDecisionType.ALLOW,
            proposal_id=prop.proposal_id,
            reason="Unwisely allowed.",
        )

    proposal = ToolCallProposal(
        proposal_id="prop-008",
        tool_name="dangerous_shell_command",
        run_id="run-001",
        arguments={"cmd": "rm -rf /"},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=allow_anything_evaluator,
    )

    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.policy_rule == "unregistered_tool_guard"
    assert result.executed is False
    assert result.error_type == "UnregisteredToolError"


def test_executor_tool_runtime_failure(base_context: dict):
    """Test that a tool throwing a runtime error marks executed=True and success=False."""
    proposal = ToolCallProposal(
        proposal_id="prop-009",
        tool_name="read_file",
        run_id="run-001",
        arguments={"path": "non_existent.txt"},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=mock_policy_evaluator,
    )

    assert decision.decision == SafetyDecisionType.ALLOW
    assert result.executed is True
    assert result.success is False
    assert result.error_type == "FileNotFoundError"


def test_executor_provider_injection(base_context: dict):
    """Test clock and id_generator injection."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    fixed_id = "test-uuid-1234"

    proposal = ToolCallProposal(
        proposal_id="prop-010",
        tool_name="calculate",
        run_id="run-001",
        arguments={"expression": "10 + 20"},
    )

    decision, result = execute_tool_action(
        proposal=proposal,
        context=base_context,
        evaluator=None,  # Will use id_generator and clock in fail-closed path
        clock=lambda: fixed_time,
        id_generator=lambda: fixed_id,
    )

    assert decision.decided_at == fixed_time
    assert decision.decision_id == f"dec-failclosed-{fixed_id}"
