"""Tests for the Bifura LangGraph agent workflow."""

from pathlib import Path
import pytest

from bifura.agent.agent import BifuraAgent
from bifura.schemas.models import EventType, SafetyDecisionType


@pytest.fixture
def agent_test_context(tmp_path: Path) -> dict:
    """Create test sandbox context with scenario_1 fixture."""
    workspace = tmp_path / "sandbox"
    runtime = workspace / "runtime"
    fixtures = workspace / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)

    # Write scenario 1 fixture
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


def test_agent_success_run(agent_test_context: dict):
    """Test full success scenario: read -> calculate -> write."""
    agent = BifuraAgent()
    result = agent.run(
        task_text="Calculate value from fixture and write result",
        scenario_id="success",
        context=agent_test_context,
        run_id="run-test-success-001",
    )

    assert result.status == "succeeded"
    assert result.final_state["read_content"] == "15 * 4"
    assert result.final_state["calculated_result"] == 60.0
    assert result.final_state["written_path"] == "result.txt"

    # Verify file was written
    result_file = Path(agent_test_context["sandbox_root"]) / "result.txt"
    assert result_file.exists()
    assert result_file.read_text(encoding="utf-8") == "60.0"

    # Verify event vocabulary and sequence
    event_types = [e.event_type for e in result.events]
    assert EventType.TASK_STARTED.value in event_types
    assert EventType.TOOL_PROPOSED.value in event_types
    assert EventType.SAFETY_DECISION.value in event_types
    assert EventType.TOOL_STARTED.value in event_types
    assert EventType.TOOL_COMPLETED.value in event_types
    assert EventType.RUN_FINISHED.value in event_types

    # Verify all decisions were ALLOW
    assert len(result.safety_decisions) == 3
    for dec in result.safety_decisions:
        assert dec.decision == SafetyDecisionType.ALLOW


def test_agent_wrong_path_blocked(agent_test_context: dict):
    """Test wrong_path scenario where path traversal is blocked before execution."""
    agent = BifuraAgent()
    result = agent.run(
        task_text="Attempt out of scope read",
        scenario_id="wrong_path",
        context=agent_test_context,
        run_id="run-test-wrong-path-001",
    )

    assert result.status == "blocked"
    assert result.final_state["blocked"] is True

    # Confirm BLOCK decision and tool_blocked event
    assert len(result.safety_decisions) >= 1
    assert result.safety_decisions[0].decision == SafetyDecisionType.BLOCK

    event_types = [e.event_type for e in result.events]
    assert EventType.TOOL_BLOCKED.value in event_types
    # Tool must NEVER have started or completed
    assert EventType.TOOL_STARTED.value not in event_types
    assert EventType.TOOL_COMPLETED.value not in event_types
