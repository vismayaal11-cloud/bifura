"""Tests for the 4 standardized Bifura demo scenarios."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from bifura.agent.scenarios import get_scenario_context, run_scenario
from bifura.schemas.models import EventType, RunStatus, SafetyDecisionType


@pytest.fixture
def scenario_test_env(tmp_path: Path) -> dict:
    """Setup an isolated workspace and runtime tree with scenario_1.txt fixture."""
    workspace = tmp_path / "data" / "sandbox"
    runtime = workspace / "runtime"
    fixtures = workspace / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)

    # Place canonical fixture
    (fixtures / "scenario_1.txt").write_text("15 * 4", encoding="utf-8")

    return {
        "repo_root": tmp_path,
        "workspace": workspace,
        "runtime": runtime,
    }


def test_scenario_success(scenario_test_env: dict):
    """Test full execution of the 'success' scenario."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bundle = run_scenario(
        scenario_id="success",
        repo_root=scenario_test_env["repo_root"],
        clock=lambda: fixed_time,
        export_bundle=False,
        run_id="run-success-001",
    )

    # 1. Run record checks
    assert bundle.scenario_id == "success"
    assert bundle.run.status == "succeeded"
    assert bundle.run.run_id == "run-success-001"

    # 2. File output check
    result_file = scenario_test_env["runtime"] / "result.txt"
    assert result_file.exists()
    assert result_file.read_text(encoding="utf-8") == "60.0"

    # 3. Deviation check
    assert bundle.deviation is not None
    assert bundle.deviation.found is False
    assert bundle.deviation.first_deviation_event_id is None

    # 4. Decisions check
    assert len(bundle.safety_decisions) == 3
    for dec in bundle.safety_decisions:
        assert dec.decision == SafetyDecisionType.ALLOW

    # 5. Impact graph check (dataflow dependencies exist)
    assert bundle.impact_graph is not None
    assert len(bundle.impact_graph.edges) >= 1


def test_scenario_wrong_path(scenario_test_env: dict):
    """Test blocked execution of the 'wrong_path' scenario."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bundle = run_scenario(
        scenario_id="wrong_path",
        repo_root=scenario_test_env["repo_root"],
        clock=lambda: fixed_time,
        export_bundle=False,
        run_id="run-wrong-path-001",
    )

    # 1. Run record checks
    assert bundle.scenario_id == "wrong_path"
    assert bundle.run.status == "blocked"

    # 2. Deviation check
    assert bundle.deviation is not None
    assert bundle.deviation.found is True
    assert bundle.deviation.first_deviation_event_id is not None

    # 3. Event verification
    events = bundle.events
    blocked_events = [e for e in events if e.event_type == EventType.TOOL_BLOCKED.value]
    assert len(blocked_events) == 1
    assert bundle.deviation.first_deviation_event_id == blocked_events[0].event_id

    # 4. Confirm zero outside files were accessed or written
    assert not (scenario_test_env["runtime"] / "result.txt").exists()


def test_scenario_stale_state(scenario_test_env: dict):
    """Test the 'stale_state' controlled fault scenario."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bundle = run_scenario(
        scenario_id="stale_state",
        repo_root=scenario_test_env["repo_root"],
        clock=lambda: fixed_time,
        export_bundle=False,
        run_id="run-stale-001",
    )

    # 1. Run record checks
    assert bundle.scenario_id == "stale_state"
    assert bundle.run.status == "failed"
    assert "controlled fault injection; deterministic planner, no llm" in bundle.actual_execution_summary.lower()

    # 2. Deviation check
    assert bundle.deviation is not None
    assert bundle.deviation.found is True
    assert bundle.deviation.first_deviation_event_id is not None

    # First deviation must be the assertion_failed event
    first_dev_event = next(e for e in bundle.events if e.event_id == bundle.deviation.first_deviation_event_id)
    assert first_dev_event.event_type == EventType.ASSERTION_FAILED.value
    assert "Discrepancy" in first_dev_event.summary


def test_scenario_wrong_sequence(scenario_test_env: dict):
    """Test the 'wrong_sequence' controlled fault scenario."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bundle = run_scenario(
        scenario_id="wrong_sequence",
        repo_root=scenario_test_env["repo_root"],
        clock=lambda: fixed_time,
        export_bundle=False,
        run_id="run-sequence-001",
    )

    # 1. Run record checks
    assert bundle.scenario_id == "wrong_sequence"
    assert bundle.run.status == "failed"
    assert "controlled fault injection; deterministic planner, no llm" in bundle.actual_execution_summary.lower()

    # 2. Deviation check
    assert bundle.deviation is not None
    assert bundle.deviation.found is True
    assert bundle.deviation.first_deviation_event_id is not None

    # First deviation must be the sequence invariant assertion failure
    first_dev_event = next(e for e in bundle.events if e.event_id == bundle.deviation.first_deviation_event_id)
    assert first_dev_event.event_type == EventType.ASSERTION_FAILED.value
    assert "Workflow precondition violated" in first_dev_event.summary


def test_scenario_determinism(scenario_test_env: dict):
    """Test that two runs with identical clock and id generator produce identical bundles."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def id_gen_1():
        seq = [f"id-{i:03d}" for i in range(100)]
        it = iter(seq)
        return lambda: next(it)

    bundle1 = run_scenario(
        scenario_id="success",
        repo_root=scenario_test_env["repo_root"],
        clock=lambda: fixed_time,
        id_generator=id_gen_1(),
        export_bundle=False,
        run_id="run-det-001",
    )

    bundle2 = run_scenario(
        scenario_id="success",
        repo_root=scenario_test_env["repo_root"],
        clock=lambda: fixed_time,
        id_generator=id_gen_1(),
        export_bundle=False,
        run_id="run-det-001",
    )

    assert bundle1.model_dump(mode="json") == bundle2.model_dump(mode="json")
