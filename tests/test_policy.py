"""Tests for deterministic safety policy evaluator (Member 2 ownership)."""

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from bifura.schemas.models import (
    ExecutionStatus,
    SafetyDecisionType,
    ToolCallProposal,
)
from bifura.tools.policy import evaluate_tool_action


def _make_context(
    mode: str = "demo",
    write_sandbox: bool = True,
    write_project: bool = False,
    allow_network: bool = False,
    workspace_root: str = "data/sandbox/",
    sandbox_root: str = "data/sandbox/runtime/",
    allowed_tools: list[str] | None = None,
) -> dict:
    if allowed_tools is None:
        allowed_tools = ["read_file", "calculate", "write_file"]
    return {
        "mode": mode,
        "workspace_root": workspace_root,
        "sandbox_root": sandbox_root,
        "allowed_tools": allowed_tools,
        "permissions": {
            "write_sandbox": write_sandbox,
            "write_project": write_project,
            "allow_network": allow_network,
        },
        "provenance": "trusted_orchestrator",
    }


def test_missing_context_keys_blocks():
    """Verify evaluator blocks when required context keys are missing."""
    proposal = ToolCallProposal(
        proposal_id="prop-001",
        run_id="run-001",
        tool_name="read_file",
        arguments={"path": "fixtures/scenario_1.txt"},
    )
    decision = evaluate_tool_action(proposal, {})
    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION
    assert decision.policy_rule == "invalid_context"
    assert "workspace_root" in decision.reason


def test_unauthorized_tool_blocks():
    """Verify tool not in allowed_tools list is blocked."""
    context = _make_context(allowed_tools=["read_file"])
    proposal = ToolCallProposal(
        proposal_id="prop-002",
        run_id="run-001",
        tool_name="calculate",
        arguments={"expression": "1 + 1"},
    )
    decision = evaluate_tool_action(proposal, context)
    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.policy_rule == "unauthorized_tool"
    assert decision.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION


def test_read_file_allow_within_workspace():
    """Valid relative path strictly inside workspace is allowed."""
    context = _make_context()
    proposal = ToolCallProposal(
        proposal_id="prop-003",
        run_id="run-001",
        tool_name="read_file",
        arguments={"path": "fixtures/scenario_1.txt"},
    )
    decision = evaluate_tool_action(proposal, context)
    assert decision.decision == SafetyDecisionType.ALLOW
    assert decision.execution_status == ExecutionStatus.NOT_STARTED
    assert decision.policy_rule == "workspace_containment"
    assert decision.validated_target is not None


@pytest.mark.parametrize(
    "invalid_path",
    [
        "../../secrets.txt",
        "../outside.txt",
        "fixtures/../../outside.txt",
        "/etc/passwd",
        "\\windows\\system32",
        "C:\\secrets.txt",
        "\\\\server\\share\\file.txt",
        "file.txt:stream",
        "CON",
        "NUL.txt",
        "aux",
        ".env",
        ".git/config",
        ".venv/pyvenv.cfg",
        "id_rsa",
        "",
        "   ",
    ],
)
def test_read_file_blocks_path_traversal_and_malformed(invalid_path: str):
    """Path traversal, absolute, drive, UNC, device names, and protected resources are blocked."""
    context = _make_context()
    proposal = ToolCallProposal(
        proposal_id="prop-traversal",
        run_id="run-001",
        tool_name="read_file",
        arguments={"path": invalid_path},
    )
    decision = evaluate_tool_action(proposal, context)
    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION


def test_write_file_allow_inside_sandbox_with_permission():
    """Write strictly inside sandbox_root with write_sandbox=True is allowed."""
    context = _make_context(write_sandbox=True)
    proposal = ToolCallProposal(
        proposal_id="prop-004",
        run_id="run-001",
        tool_name="write_file",
        arguments={"path": "result.txt", "content": "60.0"},
    )
    decision = evaluate_tool_action(proposal, context)
    assert decision.decision == SafetyDecisionType.ALLOW
    assert decision.execution_status == ExecutionStatus.NOT_STARTED
    assert decision.policy_rule == "sandbox_containment"
    assert decision.validated_target is not None


def test_write_file_blocked_when_permission_missing():
    """Write without write_sandbox=True is blocked."""
    context = _make_context(write_sandbox=False)
    proposal = ToolCallProposal(
        proposal_id="prop-005",
        run_id="run-001",
        tool_name="write_file",
        arguments={"path": "result.txt", "content": "60.0"},
    )
    decision = evaluate_tool_action(proposal, context)
    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION
    assert decision.policy_rule == "sandbox_write_permission"


def test_write_file_blocked_when_escaping_sandbox_root():
    """Write target escaping sandbox_root (even if inside workspace_root) is blocked."""
    context = _make_context(
        workspace_root="data/sandbox/",
        sandbox_root="data/sandbox/runtime/",
        write_sandbox=True,
    )
    # This targets data/sandbox/fixtures/test.txt which is outside runtime/
    proposal = ToolCallProposal(
        proposal_id="prop-006",
        run_id="run-001",
        tool_name="write_file",
        arguments={"path": "../fixtures/test.txt", "content": "bad"},
    )
    decision = evaluate_tool_action(proposal, context)
    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION
    assert decision.policy_rule == "sandbox_containment"


def test_write_file_blocked_when_write_project_true():
    """write_project permission is forbidden and triggers block."""
    context = _make_context(write_sandbox=True, write_project=True)
    proposal = ToolCallProposal(
        proposal_id="prop-007",
        run_id="run-001",
        tool_name="write_file",
        arguments={"path": "result.txt", "content": "data"},
    )
    decision = evaluate_tool_action(proposal, context)
    assert decision.decision == SafetyDecisionType.BLOCK
    assert decision.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION


def test_review_decision_for_ambiguous_or_human_review_actions():
    """Review status and decision returned when human authorization is required."""
    context = _make_context(allowed_tools=["read_file", "calculate", "write_file", "custom_action"])
    proposal = ToolCallProposal(
        proposal_id="prop-review-001",
        run_id="run-001",
        tool_name="custom_action",
        arguments={"data": "test"},
    )
    decision = evaluate_tool_action(proposal, context)
    assert decision.decision == SafetyDecisionType.REVIEW
    assert decision.execution_status == ExecutionStatus.AWAITING_REVIEW
    assert decision.review_status == "pending"

    # Also explicit requires_review argument
    prop_explicit = ToolCallProposal(
        proposal_id="prop-review-002",
        run_id="run-001",
        tool_name="read_file",
        arguments={"path": "fixtures/scenario_1.txt", "requires_review": True},
    )
    dec_explicit = evaluate_tool_action(prop_explicit, context)
    assert dec_explicit.decision == SafetyDecisionType.REVIEW
    assert dec_explicit.execution_status == ExecutionStatus.AWAITING_REVIEW


def test_calculator_shared_test_cases_all_pass():
    """Verify all 23 shared test cases from tests/fixtures/calculator_cases.json."""
    cases_path = Path("tests/fixtures/calculator_cases.json")
    assert cases_path.exists()

    with cases_path.open("r", encoding="utf-8") as f:
        cases_data = json.load(f)

    context = _make_context()
    for case in cases_data["cases"]:
        proposal = ToolCallProposal(
            proposal_id=f"calc-{case['id']}",
            run_id="run-calc-test",
            tool_name="calculate",
            arguments={"expression": case["expression"]},
        )
        decision = evaluate_tool_action(proposal, context)

        if case["expected_valid"]:
            assert decision.decision == SafetyDecisionType.ALLOW, (
                f"Case '{case['id']}' ({case['expression']}) was expected to be ALLOW but got {decision.decision}: {decision.reason}"
            )
            assert decision.execution_status == ExecutionStatus.NOT_STARTED
        else:
            assert decision.decision == SafetyDecisionType.BLOCK, (
                f"Case '{case['id']}' ({case['expression']}) was expected to be BLOCK but got {decision.decision}"
            )
            assert decision.execution_status == ExecutionStatus.BLOCKED_BEFORE_EXECUTION


def test_determinism_and_injected_providers():
    """Evaluator is pure and deterministic; respects injected clock and ID generator."""
    fixed_time = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
    fixed_id = "custom-dec-12345"

    context = _make_context()
    proposal = ToolCallProposal(
        proposal_id="prop-det-001",
        run_id="run-det-001",
        tool_name="read_file",
        arguments={"path": "fixtures/scenario_1.txt"},
    )

    dec1 = evaluate_tool_action(
        proposal,
        context,
        clock=lambda: fixed_time,
        id_generator=lambda: fixed_id,
    )
    dec2 = evaluate_tool_action(
        proposal,
        context,
        clock=lambda: fixed_time,
        id_generator=lambda: fixed_id,
    )

    assert dec1.decision_id == f"dec-{fixed_id}"
    assert dec1.proposal_id == "prop-det-001"
    assert dec1.decided_at == fixed_time
    assert dec1.created_at == fixed_time
    assert dec1 == dec2
