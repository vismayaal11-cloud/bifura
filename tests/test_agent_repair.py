"""Tests for bounded correction and replay."""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from bifura.agent.scenarios import run_scenario
from bifura.repair.corrector import repair_wrong_path_and_replay


def test_repair_wrong_path_and_replay(tmp_path: Path):
    """Test repairing the wrong_path scenario and verifying the replay."""
    fixed_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Generate the baseline faulty bundle (wrong_path)
    workspace = tmp_path / "baseline" / "data" / "sandbox"
    fixtures = workspace / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    (fixtures / "scenario_1.txt").write_text("15 * 4", encoding="utf-8")

    baseline_bundle = run_scenario(
        scenario_id="wrong_path",
        repo_root=tmp_path / "baseline",
        clock=lambda: fixed_time,
        export_bundle=False,
        run_id="run-baseline-wrong-path",
    )
    assert baseline_bundle.run.status == "blocked"

    # 2. Run bounded repair and replay
    disposable_root = tmp_path / "disposable_sandbox"
    replay_bundle, report = repair_wrong_path_and_replay(
        baseline_bundle=baseline_bundle,
        repo_root=tmp_path / "baseline",
        disposable_root=disposable_root,
        clock=lambda: fixed_time,
    )

    # 3. Verify report and replay bundle
    assert report.passed is True
    assert report.failures == 0
    assert report.replay_status == "passed"
    assert report.baseline_run_id == "run-baseline-wrong-path"
    assert report.corrected_run_id == replay_bundle.run.run_id
    assert "Bounded correction applied" in report.summary

    assert replay_bundle.run.status == "succeeded"
    assert replay_bundle.verification is not None
    assert replay_bundle.verification.passed is True
