"""Integration tests for the Bifura demo pipeline and end-to-end scenarios.

Verifies:
1. Real execution path: agent action proposals -> execute_tool_action() -> evaluate_tool_action().
2. Safety decisions & execution outcomes remain distinct.
3. All 4 agreed scenarios (success, wrong_path, stale_state, wrong_sequence) run end-to-end.
4. Incident memory & predictive diagnosis enrichment on run bundles.
5. Honesty rule: unverified incidents cannot be training-eligible; only verified replay enables eligibility.
6. CLI demo runner execution.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import pytest

from bifura.agent.scenarios import run_scenario
from bifura.learning.loop import record_verification
from bifura.learning.storage import IncidentStore
from bifura.repair.corrector import repair_wrong_path_and_replay
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    EventType,
    FailureCategory,
    LabelStatus,
    SafetyDecisionType,
    VerificationReport,
)
from bifura.tools.policy import evaluate_tool_action

# Ensure repo root is on sys.path for scripts import
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Import runner helpers
from scripts.run_demo import execute_demo_scenario, init_incident_store


@pytest.fixture
def demo_test_env(tmp_path: Path) -> dict:
    """Setup isolated test environment with sandbox, fixtures, and catalog."""
    workspace = tmp_path / "data" / "sandbox"
    fixtures = workspace / "fixtures"
    runtime = workspace / "runtime"
    runs_dir = tmp_path / "data" / "runs"
    incidents_dir = tmp_path / "data" / "incidents"

    fixtures.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)
    incidents_dir.mkdir(parents=True, exist_ok=True)

    # Standard sandbox fixture
    (fixtures / "scenario_1.txt").write_text("15 * 4", encoding="utf-8")

    # Copy catalog
    repo_catalog = Path("data/incidents/catalog.json")
    if repo_catalog.exists():
        (incidents_dir / "catalog.json").write_text(repo_catalog.read_text(encoding="utf-8"), encoding="utf-8")

    store = init_incident_store(incidents_dir / "catalog.json")

    return {
        "repo_root": tmp_path,
        "runs_dir": runs_dir,
        "runtime": runtime,
        "store": store,
    }


def test_demo_runner_all_scenarios_integration(demo_test_env: dict):
    """Run all four scenarios through execute_demo_scenario and assert end-to-end correctness."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    scenarios = ["success", "wrong_path", "stale_state", "wrong_sequence"]

    for sc in scenarios:
        res = execute_demo_scenario(
            scenario_id=sc,
            repo_root=demo_test_env["repo_root"],
            store=demo_test_env["store"],
            output_dir=demo_test_env["runs_dir"],
            repair=False,
            clock=lambda: fixed_time,
        )

        assert res["all_passed"] is True, f"Scenario '{sc}' failed validation checks: {res['validation_checks']}"
        assert Path(res["exported_file"]).exists()

        bundle = res["bundle"]
        assert isinstance(bundle, RunBundle)
        assert bundle.schema_version == "1.0"

        # Check real policy evaluator was used (policy rules match Member 2 policy.py)
        for dec in bundle.safety_decisions:
            assert dec.policy_rule in {
                "workspace_containment",
                "sandbox_containment",
                "safe_calculator",
                "unauthorized_tool",
            }


def test_demo_runner_success_scenario(demo_test_env: dict):
    """Test detailed contract compliance for success scenario."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    res = execute_demo_scenario(
        scenario_id="success",
        repo_root=demo_test_env["repo_root"],
        store=demo_test_env["store"],
        output_dir=demo_test_env["runs_dir"],
        clock=lambda: fixed_time,
    )

    bundle = res["bundle"]
    assert bundle.run.status == "succeeded"
    assert bundle.deviation is not None
    assert bundle.deviation.found is False

    # Check sandbox file content: 15 * 4 = 60.0
    result_file = demo_test_env["runtime"] / "result.txt"
    assert result_file.exists()
    assert result_file.read_text(encoding="utf-8").strip() == "60.0"

    # Prediction must abstain since no deviation occurred
    assert bundle.prediction is not None
    assert bundle.prediction.abstained is True
    assert "No deviation" in (bundle.prediction.abstention_reason or "")
    assert bundle.incident_records is None


def test_demo_runner_wrong_path_blocked(demo_test_env: dict):
    """Test wrong_path blocks relative path traversal before execution."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    res = execute_demo_scenario(
        scenario_id="wrong_path",
        repo_root=demo_test_env["repo_root"],
        store=demo_test_env["store"],
        output_dir=demo_test_env["runs_dir"],
        clock=lambda: fixed_time,
    )

    bundle = res["bundle"]
    assert bundle.run.status == "blocked"

    # Decision must be BLOCK before execution
    assert len(bundle.safety_decisions) >= 1
    dec = bundle.safety_decisions[0]
    assert dec.decision == SafetyDecisionType.BLOCK
    assert dec.policy_rule == "workspace_containment"
    assert dec.execution_status == "blocked_before_execution"

    # Execution result must be NOT executed
    assert len(bundle.execution_results) >= 1
    exc = bundle.execution_results[0]
    assert exc.executed is False
    assert exc.success is False
    assert exc.error_type == "SafetyBlockError"

    # Deviation must point to tool_blocked
    assert bundle.deviation is not None
    assert bundle.deviation.found is True
    blocked_event = next(e for e in bundle.events if e.event_type == EventType.TOOL_BLOCKED.value)
    assert bundle.deviation.first_deviation_event_id == blocked_event.event_id

    # Diagnosed as tool_input_validation
    assert bundle.incident_records is not None
    inc = bundle.incident_records[0]
    assert inc.failure_category == FailureCategory.TOOL_INPUT_VALIDATION
    assert inc.observed_pattern == "path_traversal_blocked"
    assert inc.training_eligible is False  # Honesty rule: unverified

    # Predicted as tool_input_validation
    assert bundle.prediction is not None
    assert FailureCategory.TOOL_INPUT_VALIDATION in bundle.prediction.predicted_categories


def test_demo_runner_stale_state_deviation(demo_test_env: dict):
    """Test stale_state allows policy-compliant actions but detects discrepancy."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    res = execute_demo_scenario(
        scenario_id="stale_state",
        repo_root=demo_test_env["repo_root"],
        store=demo_test_env["store"],
        output_dir=demo_test_env["runs_dir"],
        clock=lambda: fixed_time,
    )

    bundle = res["bundle"]
    assert bundle.run.status == "failed"

    # All safety decisions were ALLOW
    assert all(d.decision == SafetyDecisionType.ALLOW for d in bundle.safety_decisions)

    # First deviation is the invariant check detecting stale calculation input
    assert bundle.deviation is not None
    assert bundle.deviation.found is True
    assertion_event = next(e for e in bundle.events if e.event_type == EventType.ASSERTION_FAILED.value)
    assert bundle.deviation.first_deviation_event_id == assertion_event.event_id
    assert "Discrepancy" in assertion_event.summary

    # Diagnosed as state_or_dataflow
    assert bundle.incident_records is not None
    inc = bundle.incident_records[0]
    assert inc.failure_category == FailureCategory.STATE_OR_DATAFLOW
    assert inc.training_eligible is False

    # Predicted as state_or_dataflow
    assert bundle.prediction is not None
    assert FailureCategory.STATE_OR_DATAFLOW in bundle.prediction.predicted_categories


def test_demo_runner_wrong_sequence_distinction(demo_test_env: dict):
    """Test wrong_sequence distinguishes sequencing invariant failure from safety policy block."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    res = execute_demo_scenario(
        scenario_id="wrong_sequence",
        repo_root=demo_test_env["repo_root"],
        store=demo_test_env["store"],
        output_dir=demo_test_env["runs_dir"],
        clock=lambda: fixed_time,
    )

    bundle = res["bundle"]
    assert bundle.run.status == "failed"

    # Safety policy allowed the write inside sandbox
    write_dec = next(d for d in bundle.safety_decisions if d.policy_rule == "sandbox_containment")
    assert write_dec.decision == SafetyDecisionType.ALLOW

    # First deviation is sequence precondition failure, NOT a safety block
    assert bundle.deviation is not None
    assert bundle.deviation.found is True
    assertion_event = next(e for e in bundle.events if e.event_type == EventType.ASSERTION_FAILED.value)
    assert bundle.deviation.first_deviation_event_id == assertion_event.event_id
    assert "Workflow precondition" in assertion_event.summary

    # Diagnosed as planning_or_tool_sequence
    assert bundle.incident_records is not None
    inc = bundle.incident_records[0]
    assert inc.failure_category == FailureCategory.PLANNING_OR_TOOL_SEQUENCE
    assert inc.observed_pattern == "out_of_order_tool_execution"
    assert inc.training_eligible is False

    # Predicted as planning_or_tool_sequence
    assert bundle.prediction is not None
    assert FailureCategory.PLANNING_OR_TOOL_SEQUENCE in bundle.prediction.predicted_categories


def test_demo_runner_honesty_rule_and_verification(demo_test_env: dict):
    """Test that incidents become training-eligible ONLY after passing verification replay."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    store = demo_test_env["store"]

    # 1. Run wrong_path with repair=False
    res_unverified = execute_demo_scenario(
        scenario_id="wrong_path",
        repo_root=demo_test_env["repo_root"],
        store=store,
        output_dir=demo_test_env["runs_dir"],
        repair=False,
        clock=lambda: fixed_time,
    )
    unverified_inc = res_unverified["bundle"].incident_records[0]
    assert unverified_inc.training_eligible is False
    assert unverified_inc.label_status == LabelStatus.SUSPECTED
    assert res_unverified["bundle"].verification is None

    # 2. Run wrong_path with repair=True
    res_verified = execute_demo_scenario(
        scenario_id="wrong_path",
        repo_root=demo_test_env["repo_root"],
        store=store,
        output_dir=demo_test_env["runs_dir"],
        repair=True,
        clock=lambda: fixed_time,
    )
    verified_bundle = res_verified["bundle"]
    verified_inc = verified_bundle.incident_records[0]

    assert verified_bundle.verification is not None
    assert verified_bundle.verification.passed is True
    assert verified_inc.training_eligible is True
    assert verified_inc.label_status == LabelStatus.VERIFIED
    assert verified_inc.replay_status == "verified_passed"

    # 3. Simulate failed verification
    failed_report = VerificationReport(
        passed=False,
        total=1,
        failures=1,
        replay_status="failed",
        summary="Test replay failed.",
        tested_at=fixed_time,
    )
    failed_inc = record_verification(
        incident_id=verified_inc.incident_id,
        verification=failed_report,
        store=store,
    )
    assert failed_inc.training_eligible is False
    assert failed_inc.label_status == LabelStatus.SUSPECTED


def test_demo_cli_execution(tmp_path: Path):
    """Verify scripts/run_demo.py CLI execution end-to-end."""
    cli_out = tmp_path / "cli_runs"
    cli_out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "scripts/run_demo.py", "--repair", "--json", "--output-dir", str(cli_out)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))

    assert proc.returncode == 0, f"Demo CLI failed with error:\n{proc.stderr}\nOutput:\n{proc.stdout}"

    data = json.loads(proc.stdout)
    assert len(data) == 4
    for scenario_result in data:
        assert scenario_result["all_passed"] is True
        assert Path(scenario_result["exported_file"]).exists()
