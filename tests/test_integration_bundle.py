"""Validation tests for the shared starter integration run bundle."""

import json
from pathlib import Path

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
    "tool_failed",
    "tool_blocked",
    "awaiting_review",
}


def test_starter_mock_bundle_structure_and_records():
    fixture_path = Path("data/fixtures/mock_run_bundle.json")
    assert fixture_path.exists(), "Starter fixture mock_run_bundle.json must exist"

    with fixture_path.open("r", encoding="utf-8") as f:
        bundle = json.load(f)

    # 1. Top-level bundle structure & version
    assert bundle.get("schema_version") == "1.0"
    assert bundle.get("scenario_id") in {
        "success",
        "wrong_path",
        "stale_state",
        "wrong_sequence",
    }
    assert isinstance(bundle.get("expected_action_sequence"), list)
    assert isinstance(bundle.get("actual_execution_summary"), str)

    # 2. Validate nested canonical RunRecord
    run = RunRecord.model_validate(bundle["run"])
    assert run.run_id == "run-mock-001"
    assert run.status in {"blocked", "failed", "succeeded", "pending"}

    # 3. Validate nested canonical TraceEvents and agreed event vocabulary
    events = [TraceEvent.model_validate(e) for e in bundle["events"]]
    assert len(events) >= 1
    for ev in events:
        assert (
            ev.event_type in AGREED_TRACE_VOCABULARY
        ), f"Event type '{ev.event_type}' is not in agreed vocabulary"

    # 4. Validate SafetyDecisionRecord
    decisions = [
        SafetyDecisionRecord.model_validate(d)
        for d in bundle["safety_decisions"]
    ]
    assert len(decisions) >= 1
    for dec in decisions:
        assert dec.decision in {"ALLOW", "REVIEW", "BLOCK"}
        assert dec.execution_status == "blocked_before_execution"

    # 5. Validate DeviationRecord
    if bundle.get("deviation") is not None:
        deviation = DeviationRecord.model_validate(bundle["deviation"])
        assert deviation.found is True
        assert deviation.first_deviation_event_id is not None

    # 6. Validate PredictionResult and confirm score semantics
    if bundle.get("prediction") is not None:
        pred = PredictionResult.model_validate(bundle["prediction"])
        assert (
            pred.score_meaning != "probability"
            or pred.prediction_mode == "calibrated_classifier"
        ), "Uncalibrated heuristic scores must not be labelled as calibrated probability"
        assert pred.score_meaning == "heuristic_support_score"

    # 7. Validate IncidentMatch
    if bundle.get("incident_matches"):
        matches = [
            IncidentMatch.model_validate(m) for m in bundle["incident_matches"]
        ]
        assert len(matches) >= 1
        assert matches[0].similarity_score >= 0.0

    # 8. Validate ImpactGraph if present
    if bundle.get("impact_graph") is not None:
        graph = ImpactGraph.model_validate(bundle["impact_graph"])
        assert len(graph.nodes) >= 1
        assert len(graph.edges) >= 1
