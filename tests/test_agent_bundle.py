"""Tests for RunBundle model validation and filesystem export."""

import json
from datetime import datetime, timezone
from pathlib import Path
import pytest

from bifura.agent.scenarios import export_run_bundle, run_scenario
from bifura.schemas.bundle import RunBundle


@pytest.fixture
def bundle_test_env(tmp_path: Path) -> dict:
    """Setup isolated test environment for export."""
    workspace = tmp_path / "data" / "sandbox"
    runtime = workspace / "runtime"
    fixtures = workspace / "fixtures"
    runs_dir = tmp_path / "runs"
    fixtures.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    (fixtures / "scenario_1.txt").write_text("15 * 4", encoding="utf-8")

    return {
        "repo_root": tmp_path,
        "runs_dir": runs_dir,
    }


def test_export_and_load_success_bundle(bundle_test_env: dict):
    """Test exporting and re-loading a success RunBundle."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bundle = run_scenario(
        scenario_id="success",
        repo_root=bundle_test_env["repo_root"],
        clock=lambda: fixed_time,
        export_bundle=True,
        output_dir=bundle_test_env["runs_dir"],
        run_id="run-bundle-test-success",
    )

    expected_file = bundle_test_env["runs_dir"] / "run-bundle-test-success.json"
    assert expected_file.exists()

    with expected_file.open("r", encoding="utf-8") as f:
        loaded_data = json.load(f)

    # Re-validate loaded JSON via canonical RunBundle
    reloaded_bundle = RunBundle.model_validate(loaded_data)
    assert reloaded_bundle.schema_version == "1.0"
    assert reloaded_bundle.scenario_id == "success"
    assert reloaded_bundle.run.status == "succeeded"
    assert reloaded_bundle.incident_matches is None
    assert reloaded_bundle.incident_records is None
    assert reloaded_bundle.prediction is None
    assert reloaded_bundle.verification is None

    # Check deviation
    assert reloaded_bundle.deviation is not None
    assert reloaded_bundle.deviation.found is False

    # Check serialization
    dumped = reloaded_bundle.model_dump(mode="json")
    assert dumped["schema_version"] == "1.0"
    assert dumped["incident_matches"] is None


def test_export_and_load_faulty_bundle(bundle_test_env: dict):
    """Test exporting and re-loading a faulty RunBundle (wrong_path)."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    bundle = run_scenario(
        scenario_id="wrong_path",
        repo_root=bundle_test_env["repo_root"],
        clock=lambda: fixed_time,
        export_bundle=True,
        output_dir=bundle_test_env["runs_dir"],
        run_id="run-bundle-test-wrong-path",
    )

    expected_file = bundle_test_env["runs_dir"] / "run-bundle-test-wrong-path.json"
    assert expected_file.exists()

    with expected_file.open("r", encoding="utf-8") as f:
        loaded_data = json.load(f)

    reloaded_bundle = RunBundle.model_validate(loaded_data)
    assert reloaded_bundle.scenario_id == "wrong_path"
    assert reloaded_bundle.run.status == "blocked"
    assert reloaded_bundle.deviation is not None
    assert reloaded_bundle.deviation.found is True
    assert reloaded_bundle.deviation.first_deviation_event_id is not None
