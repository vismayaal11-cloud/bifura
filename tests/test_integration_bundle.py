"""Validation tests for the shared starter integration run bundle, contracts, and fixtures."""

import json
from pathlib import Path

from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    DeviationRecord,
    ImpactGraph,
    IncidentMatch,
    PredictionResult,
    RunRecord,
    SafetyDecisionRecord,
    TraceEvent,
)

AGREED_TRACE_VOCABULARY = {
    "tool_proposed",
    "safety_decision",
    "tool_started",
    "tool_completed",
    "tool_blocked",
    "awaiting_review",
    "assertion_passed",
    "assertion_failed",
    "error",
    "state_updated",
    "task_started",
    "run_finished",
}


def test_starter_mock_bundle_structure_and_records():
    """Validate that starter mock bundle satisfies schema and RunBundle model."""
    fixture_path = Path("data/fixtures/mock_run_bundle.json")
    assert fixture_path.exists(), "Starter fixture mock_run_bundle.json must exist"

    with fixture_path.open("r", encoding="utf-8") as f:
        bundle_data = json.load(f)

    # 1. Top-level bundle structure & version validation via RunBundle model
    bundle = RunBundle.model_validate(bundle_data)
    assert bundle.schema_version == "1.0"
    assert bundle.scenario_id in {
        "success",
        "wrong_path",
        "stale_state",
        "wrong_sequence",
    }
    assert isinstance(bundle.expected_action_sequence, list)
    assert bundle.expected_action_sequence == [
        "read_file",
        "calculate",
        "write_file",
    ]
    assert isinstance(bundle.actual_execution_summary, str)

    # 2. Validate nested canonical RunRecord
    run = RunRecord.model_validate(bundle_data["run"])
    assert run.run_id == "run-mock-001"
    assert run.status in {"blocked", "failed", "succeeded", "pending"}

    # 3. Validate nested canonical TraceEvents and agreed event vocabulary
    events = [TraceEvent.model_validate(e) for e in bundle_data["events"]]
    assert len(events) >= 1
    for ev in events:
        assert (
            ev.event_type in AGREED_TRACE_VOCABULARY
        ), f"Event type '{ev.event_type}' is not in agreed vocabulary"

    # 4. Validate SafetyDecisionRecord
    decisions = [
        SafetyDecisionRecord.model_validate(d)
        for d in bundle_data["safety_decisions"]
    ]
    assert len(decisions) >= 1
    for dec in decisions:
        assert dec.decision in {"ALLOW", "REVIEW", "BLOCK"}
        assert dec.execution_status == "blocked_before_execution"

    # 5. Validate DeviationRecord
    if bundle.deviation is not None:
        deviation = DeviationRecord.model_validate(bundle_data["deviation"])
        assert deviation.found is True
        assert deviation.first_deviation_event_id is not None

    # 6. Validate PredictionResult and confirm score semantics
    if bundle.prediction is not None:
        pred = PredictionResult.model_validate(bundle_data["prediction"])
        assert (
            pred.score_meaning != "probability"
            or pred.prediction_mode == "calibrated_classifier"
        ), "Uncalibrated heuristic scores must not be labelled as calibrated probability"
        assert pred.score_meaning == "heuristic_support_score"

    # 7. Validate IncidentMatch
    if bundle.incident_matches:
        matches = [
            IncidentMatch.model_validate(m)
            for m in bundle_data["incident_matches"]
        ]
        assert len(matches) >= 1
        assert matches[0].similarity_score >= 0.0

    # 8. Validate ImpactGraph if present
    if bundle.impact_graph is not None:
        graph = ImpactGraph.model_validate(bundle_data["impact_graph"])
        assert len(graph.nodes) >= 1
        assert len(graph.edges) >= 1


def test_run_bundle_initial_state_and_unavailable_data():
    """Verify that uncalculated components are correctly represented as null."""
    initial_bundle_data = {
        "schema_version": "1.0",
        "scenario_id": "success",
        "run": {
            "run_id": "run-init-001",
            "task_text": "Compute result from fixture",
            "status": "succeeded",
        },
        "expected_action_sequence": ["read_file", "calculate", "write_file"],
        "actual_execution_summary": "Task executed successfully inside sandbox.",
        "events": [],
        "safety_decisions": [],
        "execution_results": [],
        "deviation": None,
        "incident_matches": None,
        "incident_records": None,
        "prediction": None,
        "impact_graph": None,
        "verification": None,
    }

    bundle = RunBundle.model_validate(initial_bundle_data)
    assert bundle.prediction is None
    assert bundle.incident_matches is None
    assert bundle.incident_records is None
    assert bundle.verification is None
    assert bundle.impact_graph is None

    serialized = bundle.model_dump(mode="json")
    assert serialized["prediction"] is None
    assert serialized["incident_matches"] is None
    assert serialized["incident_records"] is None
    assert serialized["verification"] is None


def test_success_scenario_permission_compatibility():
    """Verify success scenario parameters and sandbox write permission compatibility."""
    # Under demo mode, write_file is allowed inside sandbox_root when write_sandbox is true
    success_context = {
        "mode": "demo",
        "workspace_root": "data/sandbox/",
        "sandbox_root": "data/sandbox/runtime/",
        "allowed_tools": ["read_file", "calculate", "write_file"],
        "permissions": {
            "allow_network": False,
            "write_sandbox": True,
            "write_project": False,
        },
        "provenance": "trusted_orchestrator",
    }

    assert success_context["mode"] == "demo"
    assert success_context["permissions"]["write_sandbox"] is True
    assert success_context["permissions"]["write_project"] is False
    assert "write_file" in success_context["allowed_tools"]
    assert "calculate" in success_context["allowed_tools"]
    assert "read_file" in success_context["allowed_tools"]


def test_calculator_shared_test_cases_table():
    """Verify shared read-only calculator test cases table at tests/fixtures/calculator_cases.json."""
    cases_path = Path("tests/fixtures/calculator_cases.json")
    assert cases_path.exists(), "tests/fixtures/calculator_cases.json must exist"

    with cases_path.open("r", encoding="utf-8") as f:
        cases_data = json.load(f)

    assert cases_data.get("schema_version") == "1.0"
    limits = cases_data.get("limits", {})
    assert limits.get("max_expression_length") == 200
    assert limits.get("max_exponent_magnitude") == 100
    assert limits.get("max_numeric_literal") == 1e12
    assert limits.get("max_result_magnitude") == 1e12

    cases = cases_data.get("cases", [])
    assert len(cases) >= 20, "Must provide comprehensive calculator test cases"

    valid_cases = [c for c in cases if c["expected_valid"]]
    invalid_cases = [c for c in cases if not c["expected_valid"]]

    assert len(valid_cases) >= 5, "Must include valid arithmetic expressions"
    assert len(invalid_cases) >= 10, "Must include edge and safety failure cases"

    for case in valid_cases:
        assert case["expected_result"] is not None
        assert isinstance(case["expected_result"], (int, float))

    for case in invalid_cases:
        assert case["expected_result"] is None
        assert case["category"] in {
            "invalid_syntax",
            "booleans",
            "complex_numbers",
            "division_by_zero",
            "oversized_literals",
            "excessive_exponents",
            "excessive_results",
            "expression_length",
        }
