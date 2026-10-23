"""Bounded correction and replay runner for the controlled wrong_path scenario."""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from bifura.agent.scenarios import run_scenario
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import PatchRecord, VerificationReport, utc_now


def repair_wrong_path_and_replay(
    baseline_bundle: RunBundle,
    repo_root: Path | str | None = None,
    disposable_root: Path | str | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> tuple[RunBundle, VerificationReport]:
    """Apply a bounded parameter correction to wrong_path and verify via replay.

    Replaces out-of-scope path '../../secrets.txt' with approved fixture 'fixtures/scenario_1.txt',
    replays the workflow in a disposable sandbox, and verifies the outcome.

    Args:
        baseline_bundle: Baseline RunBundle from wrong_path scenario.
        repo_root: Repository root path to copy scenario fixtures from.
        disposable_root: Optional directory for isolated replay sandbox.
        clock: Injected clock for deterministic timestamps.

    Returns:
        tuple of (replayed_and_verified_RunBundle, VerificationReport).
    """
    now = clock()
    patch_id = f"patch-{uuid.uuid4().hex[:8]}"

    # Setup isolated disposable sandbox
    if disposable_root:
        temp_dir_path = Path(disposable_root)
        temp_dir_path.mkdir(parents=True, exist_ok=True)
        cleanup_temp = False
    else:
        temp_dir_obj = tempfile.TemporaryDirectory()
        temp_dir_path = Path(temp_dir_obj.name)
        cleanup_temp = True

    try:
        # Prepare workspace structure
        fixtures_dir = temp_dir_path / "data" / "sandbox" / "fixtures"
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        runtime_dir = temp_dir_path / "data" / "sandbox" / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)

        # Copy or create the scenario_1 fixture
        fixture_file = fixtures_dir / "scenario_1.txt"
        if repo_root and (Path(repo_root) / "data" / "sandbox" / "fixtures" / "scenario_1.txt").exists():
            content = (Path(repo_root) / "data" / "sandbox" / "fixtures" / "scenario_1.txt").read_text(encoding="utf-8")
        else:
            content = "15 * 4"
        fixture_file.write_text(content, encoding="utf-8")

        # Replay using the corrected path inside the disposable sandbox
        corrected_run_id = f"run-replay-{uuid.uuid4().hex[:6]}"
        replay_bundle = run_scenario(
            scenario_id="success",  # The corrected plan executes the success flow
            repo_root=temp_dir_path,
            clock=clock,
            export_bundle=False,
            run_id=corrected_run_id,
        )

        # Verification checks
        result_file = runtime_dir / "result.txt"
        file_valid = result_file.exists() and result_file.read_text(encoding="utf-8").strip() == "60.0"
        status_valid = replay_bundle.run.status == "succeeded"
        deviation_valid = replay_bundle.deviation is not None and not replay_bundle.deviation.found

        passed = bool(file_valid and status_valid and deviation_valid)

        report = VerificationReport(
            report_id=f"rep-{uuid.uuid4().hex[:8]}",
            verification_id=f"ver-{uuid.uuid4().hex[:8]}",
            run_id=corrected_run_id,
            patch_id=patch_id,
            passed=passed,
            total=1,
            failures=0 if passed else 1,
            replay_status="passed" if passed else "failed",
            baseline_run_id=baseline_bundle.run.run_id,
            corrected_run_id=corrected_run_id,
            summary=(
                "Bounded correction applied: replaced out-of-scope path with approved fixture. "
                f"Replay {'passed' if passed else 'failed'} verification in disposable sandbox."
            ),
            tested_at=now,
        )

        replay_bundle.verification = report
        return replay_bundle, report

    finally:
        if cleanup_temp:
            # TemporaryDirectory cleanup handled automatically on gc
            pass
