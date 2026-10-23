"""Tests for Bifura Streamlit dashboard and bundle loader (Member 2 ownership)."""

import json
from pathlib import Path
import tempfile

import pytest
from streamlit.testing.v1 import AppTest

from bifura.dashboard.loader import discover_and_load_bundles
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    DependencyEdge,
    ImpactGraph,
    RunRecord,
    TraceEvent,
)


def test_discover_and_load_bundles_from_fixtures():
    """Verify loader successfully scans and loads all valid fixtures."""
    loaded_runs, load_errors = discover_and_load_bundles(
        fixtures_dir="data/fixtures",
        runs_dir="data/runs",
    )

    assert len(loaded_runs) >= 4, "Must load at least the 4 standard scenario fixtures"
    assert len(load_errors) == 0, f"Expected no load errors on valid fixtures, got: {load_errors}"

    scenario_ids = {item.bundle.scenario_id for item in loaded_runs.values()}
    assert "success" in scenario_ids
    assert "wrong_path" in scenario_ids
    assert "stale_state" in scenario_ids
    assert "wrong_sequence" in scenario_ids

    # Verify each item wraps a validated RunBundle
    for key, item in loaded_runs.items():
        assert isinstance(item.bundle, RunBundle)
        assert item.bundle.schema_version == "1.0"
        assert item.source_type == "fixture"


def test_loader_handles_missing_runtime_directory_gracefully():
    """Verify loader handles non-existent runs directory without crashing."""
    non_existent_dir = Path("data/runs_non_existent_dir_test")
    assert not non_existent_dir.exists()

    loaded_runs, load_errors = discover_and_load_bundles(
        fixtures_dir="data/fixtures",
        runs_dir=non_existent_dir,
    )
    assert len(loaded_runs) >= 4
    assert len(load_errors) == 0


def test_loader_handles_malformed_json_and_invalid_schema():
    """Verify loader records friendly errors for invalid JSON or records instead of crashing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Malformed JSON file
        bad_json = tmp_path / "corrupted.json"
        bad_json.write_text("{ this is not valid json :", encoding="utf-8")

        # 2. Invalid schema (missing mandatory scenario_id & run)
        bad_schema = tmp_path / "invalid_schema.json"
        bad_schema.write_text(
            json.dumps({"schema_version": "1.0", "unknown_field": True}),
            encoding="utf-8",
        )

        loaded_runs, load_errors = discover_and_load_bundles(
            fixtures_dir=tmp_path,
            runs_dir=tmp_path / "empty_sub",
        )

        assert len(loaded_runs) == 0
        assert len(load_errors) == 2

        error_types = {err["error_type"] for err in load_errors}
        assert "JSONDecodeError" in error_types
        assert "ValidationError" in error_types


def test_all_scenario_fixtures_expected_statuses():
    """Verify each scenario fixture conforms to agreed status and sequence specifications."""
    scenario_expectations = {
        "success": "succeeded",
        "wrong_path": "blocked",
        "stale_state": "failed",
        "wrong_sequence": "failed",
    }

    for scenario_id, expected_status in scenario_expectations.items():
        fixture_path = Path(f"data/fixtures/{scenario_id}.json")
        assert fixture_path.exists(), f"Fixture {fixture_path} must exist"

        with fixture_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        bundle = RunBundle.model_validate(data)
        assert bundle.scenario_id == scenario_id

        actual_status = getattr(bundle.run.status, "value", str(bundle.run.status))
        assert actual_status == expected_status, (
            f"Scenario {scenario_id} expected status '{expected_status}', got '{actual_status}'"
        )

        assert bundle.expected_action_sequence == [
            "read_file",
            "calculate",
            "write_file",
        ]

        # Verify score meaning for heuristic predictions
        if bundle.prediction is not None:
            assert bundle.prediction.score_meaning == "heuristic_support_score", (
                f"Prediction in {scenario_id} must have score_meaning 'heuristic_support_score'"
            )


def test_missing_optional_data_bundle():
    """Verify bundle with null optional components validates cleanly."""
    bundle = RunBundle(
        scenario_id="success",
        run=RunRecord(run_id="run-test-null", status="succeeded"),
        expected_action_sequence=["read_file", "calculate", "write_file"],
        actual_execution_summary="Minimal bundle test",
        events=[],
        safety_decisions=[],
        execution_results=[],
        deviation=None,
        incident_matches=None,
        incident_records=None,
        prediction=None,
        impact_graph=None,
        verification=None,
    )
    assert bundle.deviation is None
    assert bundle.prediction is None
    assert bundle.incident_matches is None
    assert bundle.impact_graph is None
    assert bundle.verification is None


def test_impact_graph_handles_both_edge_shapes():
    """Verify impact graph edges processing handles both DependencyEdge and dict shapes."""
    edge_obj = DependencyEdge(
        from_event_id="ev-001",
        to_event_id="ev-002",
        dependency_type="control_flow",
        explanation="Object edge test",
    )
    edge_dict = {
        "from_event_id": "ev-002",
        "to_event_id": "ev-003",
        "dependency_type": "consumes_output",
        "explanation": "Dict edge test",
    }

    # Verify attributes/keys extraction for both shapes
    for edge in [edge_obj, edge_dict]:
        from_id = edge.from_event_id if isinstance(edge, DependencyEdge) else edge.get("from_event_id")
        to_id = edge.to_event_id if isinstance(edge, DependencyEdge) else edge.get("to_event_id")
        dep_type = edge.dependency_type if isinstance(edge, DependencyEdge) else edge.get("dependency_type")
        assert from_id in {"ev-001", "ev-002"}
        assert to_id in {"ev-002", "ev-003"}
        assert dep_type in {"control_flow", "consumes_output"}


def test_streamlit_app_smoke_test():
    """Smoke test app.py with streamlit.testing.v1.AppTest."""
    app_path = Path(__file__).parent.parent / "app.py"
    assert app_path.exists(), f"app.py must exist at {app_path}"

    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run(timeout=15)

    assert not at.exception, f"AppTest raised an unhandled exception: {at.exception}"

    # Verify sidebar selectbox exists and holds loaded options
    assert len(at.sidebar.selectbox) >= 1
    run_select = at.sidebar.selectbox[0]
    assert len(run_select.options) >= 4

    # Test selecting the second scenario
    run_select.select_index(1)
    at.run(timeout=15)
    assert not at.exception
