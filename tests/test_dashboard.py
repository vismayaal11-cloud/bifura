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
        assert item.source_type in ("fixture", "runtime")


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


def test_timeline_and_components_render_no_literal_html_tags():
    """Verify that event timeline and component cards do not leak literal HTML tags into markdown."""
    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run(timeout=15)

    assert not at.exception

    # Inspect all markdown elements except the CSS <style> block
    for md in at.markdown:
        val = md.value
        if "<style>" in val:
            continue
        # Verify no raw unparsed HTML tags are rendered inside cards
        assert "<span style=" not in val, f"Found unparsed literal <span style=...>: {val}"
        assert "<div class=" not in val, f"Found unparsed literal <div class=...>: {val}"
        assert "<span class=" not in val, f"Found unparsed literal <span class=...>: {val}"


def test_runtime_run_discovery_and_selection_including_wrong_path():
    """Verify loader discovers runtime bundles in data/runs/ and app selectbox can select run-wrong_path-20261023191417."""
    loaded_runs, load_errors = discover_and_load_bundles(
        fixtures_dir="data/fixtures",
        runs_dir="data/runs",
    )

    # Confirm run selector distinguishes fixtures and runtime bundles
    runtime_runs = {k: v for k, v in loaded_runs.items() if v.source_type == "runtime"}
    fixture_runs = {k: v for k, v in loaded_runs.items() if v.source_type == "fixture"}

    assert len(fixture_runs) >= 4, "Must load standard fixtures"
    assert len(runtime_runs) >= 1, "Must load generated runtime runs from data/runs"

    for r in fixture_runs.values():
        assert "[FIXTURE]" in r.display_label
    for r in runtime_runs.values():
        assert "[RUNTIME]" in r.display_label

    # Target specific runtime run requested by user
    target_key = next((k for k in loaded_runs if "run-wrong_path-20261023191417" in k), None)
    assert target_key is not None, "Target runtime run run-wrong_path-20261023191417 must be discovered"

    target_run = loaded_runs[target_key]
    assert target_run.source_type == "runtime"
    assert target_run.bundle.scenario_id == "wrong_path"
    status_str = getattr(target_run.bundle.run.status, "value", str(target_run.bundle.run.status))
    assert status_str == "blocked"
    assert target_run.bundle.deviation is not None
    assert target_run.bundle.prediction is not None
    assert target_run.bundle.verification is not None

    # Test selecting this specific runtime run inside Streamlit AppTest
    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run(timeout=15)

    assert not at.exception
    run_select = at.sidebar.selectbox[0]

    # Select the target runtime run
    run_select.select(target_key)
    at.run(timeout=15)

    assert not at.exception
    # Verify no unparsed HTML tags in the selected runtime run view
    for md in at.markdown:
        if "<style>" in md.value:
            continue
        assert "<span style=" not in md.value
        assert "<div class=" not in md.value


def test_source_type_filter_in_sidebar():
    """Verify that the sidebar source filter can isolate runtime runs vs fixtures."""
    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run(timeout=15)

    assert not at.exception
    assert len(at.sidebar.radio) >= 1

    # Filter to Runtime Runs Only
    at.sidebar.radio[0].set_value("Runtime Runs Only")
    at.run(timeout=15)
    assert not at.exception

    run_select = at.sidebar.selectbox[0]
    for opt in run_select.options:
        assert "[RUNTIME]" in opt, f"Expected only runtime runs when filtered, got: {opt}"

    # Filter to Fixtures Only
    at.sidebar.radio[0].set_value("Fixtures Only")
    at.run(timeout=15)
    assert not at.exception

    run_select = at.sidebar.selectbox[0]
    for opt in run_select.options:
        assert "[FIXTURE]" in opt, f"Expected only fixture runs when filtered, got: {opt}"


def test_task_started_and_run_finished_no_raw_html_regression():
    """Regression test ensuring task_started and run_finished do not leak raw HTML markup into event text."""
    app_path = Path(__file__).parent.parent / "app.py"
    at = AppTest.from_file(str(app_path), default_timeout=15)
    at.run(timeout=15)

    assert not at.exception

    # Select the runtime wrong_path scenario if available, otherwise a scenario with task_started/run_finished
    target_opt = next(
        (opt for opt in at.sidebar.selectbox[0].options if "wrong_path" in opt and "[RUNTIME]" in opt),
        next((opt for opt in at.sidebar.selectbox[0].options if "success" in opt), at.sidebar.selectbox[0].options[0]),
    )
    at.sidebar.selectbox[0].select(target_opt)
    at.run(timeout=15)

    assert not at.exception

    # Locate markdown and caption entries for task_started and run_finished
    task_started_entries = [m.value for m in at.markdown if "task_started" in m.value]
    run_finished_entries = [m.value for m in at.markdown if "run_finished" in m.value]

    assert len(task_started_entries) >= 1, "task_started event must be rendered in timeline"
    assert len(run_finished_entries) >= 1, "run_finished event must be rendered in timeline"

    for entry in task_started_entries + run_finished_entries:
        assert "<span style=" not in entry, f"Found raw <span style=...> in event: {entry}"
        assert "<div style=" not in entry, f"Found raw <div style=...> in event: {entry}"
        assert "<span" not in entry, f"Found raw <span...> in event: {entry}"
        assert "<div" not in entry, f"Found raw <div...> in event: {entry}"

    # Verify timestamps are displayed cleanly via native captions
    timestamp_captions = [c.value for c in at.caption if c.value.startswith("🕒")]
    assert len(timestamp_captions) >= 2, "Timestamps for events must be rendered cleanly via native captions"
    for ts in timestamp_captions:
        assert "<span" not in ts
        assert "<div" not in ts
        assert "style=" not in ts

    # Verify descriptions / summaries for task_started and run_finished do not leak HTML
    all_captions = [c.value for c in at.caption]
    for cap in all_captions:
        assert "<span style=" not in cap
        assert "<div style=" not in cap
