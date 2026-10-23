"""Tests for Bifura learning module: storage, diagnosis, retrieval, prediction, and learning loop."""

import pytest
from pathlib import Path
from datetime import datetime, timezone

from bifura.schemas.models import (
    DeviationRecord,
    FailureCategory,
    IncidentMatch,
    IncidentRecord,
    LabelStatus,
    RunRecord,
    TraceEvent,
)
from bifura.schemas.bundle import RunBundle
from bifura.learning import (
    DuplicateIncidentError,
    IncidentStore,
    calculate_incident_similarity,
    diagnose_run_bundle,
    retrieve_similar_incidents,
)


def _make_sample_incident(
    incident_id: str = "inc-test-001",
    run_id: str = "run-test-001",
    category: FailureCategory = FailureCategory.TOOL_INPUT_VALIDATION,
    label_status: LabelStatus = LabelStatus.SUSPECTED,
    training_eligible: bool = False,
    pattern: str = "path_traversal",
) -> IncidentRecord:
    return IncidentRecord(
        incident_id=incident_id,
        run_id=run_id,
        source_run_id=run_id,
        task_summary="Test task execution",
        observed_pattern=pattern,
        expected_behavior="Target within sandbox root",
        observed_behavior="Target escaped workspace",
        first_deviation_event_id="ev-001",
        failure_category=category,
        label_status=label_status,
        root_cause_status="suspected" if label_status == LabelStatus.SUSPECTED else "verified",
        root_cause_summary="Path traversal attempted",
        root_cause_hypotheses=["User or model provided relative path escaping sandbox"],
        evidence_refs=["ev-001", "dec-001"],
        affected_event_ids=["ev-001"],
        data_origin="controlled_fixture",
        provenance="controlled_fixture",
        training_eligible=training_eligible,
        training_eligibility="eligible" if training_eligible else "pending_review",
        review_status="reviewed" if label_status != LabelStatus.SUSPECTED else "pending",
        replay_status="not_run",
        dataset_version="dataset-v1",
    )


class TestIncidentStore:
    """Test suite for SQLite-backed IncidentStore (Critical Step 1)."""

    def test_store_and_retrieve_incident(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test_incidents.db"
        store = IncidentStore(db_path=db_file)

        incident = _make_sample_incident()
        store.add_incident(incident)

        retrieved = store.get_incident(incident.incident_id)
        assert retrieved is not None
        assert isinstance(retrieved, IncidentRecord)
        assert retrieved.incident_id == incident.incident_id
        assert retrieved.failure_category == FailureCategory.TOOL_INPUT_VALIDATION
        assert retrieved.observed_pattern == "path_traversal"
        assert retrieved.first_deviation_event_id == "ev-001"
        assert retrieved.evidence_refs == ["ev-001", "dec-001"]
        assert retrieved.root_cause_hypotheses == [
            "User or model provided relative path escaping sandbox"
        ]

    def test_store_duplicate_id_raises_error(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test_duplicates.db"
        store = IncidentStore(db_path=db_file)

        incident = _make_sample_incident(incident_id="inc-dup-001")
        store.add_incident(incident)

        with pytest.raises(DuplicateIncidentError):
            store.add_incident(incident)

    def test_honesty_rule_suspected_cannot_be_training_eligible(
        self, tmp_path: Path
    ) -> None:
        db_file = tmp_path / "test_honesty.db"
        store = IncidentStore(db_path=db_file)

        # Attempt to store suspected incident with training_eligible=True
        invalid_incident = _make_sample_incident(
            incident_id="inc-dishonest-001",
            label_status=LabelStatus.SUSPECTED,
            training_eligible=True,
        )

        with pytest.raises(ValueError, match="Honesty violation"):
            store.add_incident(invalid_incident)

    def test_update_incident_and_verification(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test_update.db"
        store = IncidentStore(db_path=db_file)

        incident = _make_sample_incident(
            incident_id="inc-update-001",
            label_status=LabelStatus.SUSPECTED,
            training_eligible=False,
        )
        store.add_incident(incident)

        # Update to verified and training_eligible
        updated = incident.model_copy(
            update={
                "label_status": LabelStatus.VERIFIED,
                "training_eligible": True,
                "verified_root_cause": "Path traversal confirmed by policy violation replay",
                "verified_correction": "Normalize and contain path inside sandbox root",
                "replay_status": "verified_passed",
            }
        )
        store.update_incident(updated)

        retrieved = store.get_incident("inc-update-001")
        assert retrieved is not None
        assert retrieved.label_status == LabelStatus.VERIFIED
        assert retrieved.training_eligible is True
        assert retrieved.verified_root_cause is not None
        assert retrieved.replay_status == "verified_passed"

    def test_list_and_filter_incidents(self, tmp_path: Path) -> None:
        db_file = tmp_path / "test_filter.db"
        store = IncidentStore(db_path=db_file)

        inc1 = _make_sample_incident(
            incident_id="inc-01",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            label_status=LabelStatus.SUSPECTED,
            training_eligible=False,
        )
        inc2 = _make_sample_incident(
            incident_id="inc-02",
            category=FailureCategory.STATE_OR_DATAFLOW,
            label_status=LabelStatus.VERIFIED,
            training_eligible=True,
        )
        inc3 = _make_sample_incident(
            incident_id="inc-03",
            category=FailureCategory.PLANNING_OR_TOOL_SEQUENCE,
            label_status=LabelStatus.VERIFIED,
            training_eligible=True,
        )

        store.add_incident(inc1)
        store.add_incident(inc2)
        store.add_incident(inc3)

        assert store.count_incidents() == 3

        cat_filtered = store.list_incidents(
            failure_category=FailureCategory.STATE_OR_DATAFLOW
        )
        assert len(cat_filtered) == 1
        assert cat_filtered[0].incident_id == "inc-02"

        eligible_filtered = store.list_incidents(training_eligible_only=True)
        assert len(eligible_filtered) == 2
        assert {i.incident_id for i in eligible_filtered} == {"inc-02", "inc-03"}

    def test_isolated_database_environments(self, tmp_path: Path) -> None:
        db1 = tmp_path / "db1.db"
        db2 = tmp_path / "db2.db"

        store1 = IncidentStore(db_path=db1)
        store2 = IncidentStore(db_path=db2)

        store1.add_incident(_make_sample_incident(incident_id="inc-db1"))

        assert store1.get_incident("inc-db1") is not None
        assert store2.get_incident("inc-db1") is None
        assert store1.count_incidents() == 1
        assert store2.count_incidents() == 0


class TestDiagnosis:
    """Test suite for bundle diagnosis (Critical Step 2)."""

    def test_diagnose_success_scenario_returns_none(self) -> None:
        bundle = RunBundle(
            scenario_id="success",
            run=RunRecord(run_id="run-success-001", status="succeeded"),
            deviation=DeviationRecord(run_id="run-success-001", found=False),
        )
        incident = diagnose_run_bundle(bundle)
        assert incident is None

    def test_diagnose_wrong_path_from_fixture_file(self) -> None:
        import json
        with open("data/fixtures/mock_run_bundle.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        bundle = RunBundle.model_validate(data)

        incident = diagnose_run_bundle(bundle)
        assert incident is not None
        assert incident.failure_category == FailureCategory.TOOL_INPUT_VALIDATION
        assert incident.observed_pattern == "path_traversal_blocked"
        assert incident.label_status == LabelStatus.SUSPECTED
        assert incident.training_eligible is False
        assert "dec-mock-001" in incident.evidence_refs
        assert "ev-001" in incident.evidence_refs

    def test_diagnose_stale_state_scenario(self) -> None:
        bundle = RunBundle(
            scenario_id="stale_state",
            run=RunRecord(
                run_id="run-stale-001",
                task_text="Perform sequential computation",
                status="failed",
            ),
            expected_action_sequence=["read_file", "calculate", "write_file"],
            actual_execution_summary="Agent calculated with stale cached input 2 + 3 instead of 15 * 4",
            events=[
                TraceEvent(
                    run_id="run-stale-001",
                    event_id="ev-01",
                    sequence=1,
                    event_type="tool_completed",
                    tool_name="read_file",
                    output_data={"content": "15 * 4"},
                ),
                TraceEvent(
                    run_id="run-stale-001",
                    event_id="ev-02",
                    sequence=2,
                    event_type="assertion_failed",
                    summary="Discrepancy detected: stale input expression 2 + 3 does not match file content 15 * 4",
                    error="stale state mismatch",
                ),
            ],
            deviation=DeviationRecord(
                run_id="run-stale-001",
                found=True,
                first_deviation_event_id="ev-02",
                expected={"expression": "15 * 4"},
                actual={"expression": "2 + 3"},
                expected_behavior="Calculator receives expression from freshly read file",
                observed_behavior="Calculator received stale cached value 2 + 3",
                description="Stale state discrepancy in calculation input",
            ),
        )

        incident = diagnose_run_bundle(bundle)
        assert incident is not None
        assert incident.failure_category == FailureCategory.STATE_OR_DATAFLOW
        assert incident.observed_pattern == "stale_state_or_dataflow_mismatch"
        assert "ev-02" in incident.evidence_refs

    def test_diagnose_wrong_sequence_scenario(self) -> None:
        bundle = RunBundle(
            scenario_id="wrong_sequence",
            run=RunRecord(
                run_id="run-seq-001",
                task_text="Read, calculate and write",
                status="failed",
            ),
            expected_action_sequence=["read_file", "calculate", "write_file"],
            actual_execution_summary="Agent proposed write_file before calculation completed",
            events=[
                TraceEvent(
                    run_id="run-seq-001",
                    event_id="ev-s01",
                    sequence=1,
                    event_type="tool_completed",
                    tool_name="read_file",
                ),
                TraceEvent(
                    run_id="run-seq-001",
                    event_id="ev-s02",
                    sequence=2,
                    event_type="tool_proposed",
                    tool_name="write_file",
                    input_data={"path": "result.txt", "content": "uncomputed"},
                ),
                TraceEvent(
                    run_id="run-seq-001",
                    event_id="ev-s03",
                    sequence=3,
                    event_type="assertion_failed",
                    summary="Sequence precondition violated: write_file attempted before calculate",
                ),
            ],
            deviation=DeviationRecord(
                run_id="run-seq-001",
                found=True,
                first_deviation_event_id="ev-s02",
                expected_behavior="calculate completes before write_file",
                observed_behavior="write_file proposed prematurely",
                description="Out of order execution sequence",
            ),
        )

        incident = diagnose_run_bundle(bundle)
        assert incident is not None
        assert incident.failure_category == FailureCategory.PLANNING_OR_TOOL_SEQUENCE
        assert incident.observed_pattern == "out_of_order_tool_execution"

    def test_diagnose_unknown_insufficient_evidence(self) -> None:
        bundle = RunBundle(
            scenario_id="ambiguous_scenario",
            run=RunRecord(run_id="run-amb-001", status="failed"),
            deviation=DeviationRecord(
                run_id="run-amb-001",
                found=True,
                description="Something anomalous happened without clear log trace",
            ),
        )

        incident = diagnose_run_bundle(bundle)
        assert incident is not None
        assert (
            incident.failure_category
            == FailureCategory.UNKNOWN_INSUFFICIENT_EVIDENCE
        )
        assert incident.observed_pattern == "unclassified_deviation"

    def test_deterministic_id_and_clock_injection(self) -> None:
        fixed_dt = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
        bundle = RunBundle(
            scenario_id="wrong_path",
            run=RunRecord(run_id="run-inj-001", status="blocked"),
            deviation=DeviationRecord(
                run_id="run-inj-001",
                found=True,
                description="Path traversal attempt blocked",
            ),
        )

        incident = diagnose_run_bundle(
            bundle,
            id_generator=lambda: "inc-custom-fixed-id",
            clock=lambda: fixed_dt,
        )
        assert incident is not None
        assert incident.incident_id == "inc-custom-fixed-id"
        assert incident.created_at == fixed_dt


class TestRetrieval:
    """Test suite for structured similar incident retrieval (Critical Step 3)."""

    def test_retrieve_relevant_match(self) -> None:
        query_inc = _make_sample_incident(
            incident_id="inc-query",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            pattern="path_traversal_blocked",
        )
        cand1 = _make_sample_incident(
            incident_id="inc-hist-match",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            pattern="path_traversal_blocked",
        )
        cand2 = _make_sample_incident(
            incident_id="inc-hist-diff",
            category=FailureCategory.STATE_OR_DATAFLOW,
            pattern="stale_state_or_dataflow_mismatch",
        )

        matches = retrieve_similar_incidents(
            query=query_inc,
            candidates=[cand1, cand2],
            top_k=5,
            min_similarity=0.1,
        )

        assert len(matches) >= 1
        top_match = matches[0]
        assert top_match.incident_id == "inc-hist-match"
        assert 0.0 <= top_match.similarity_score <= 1.0
        assert top_match.similarity_score > 0.60
        assert top_match.score_kind == "similarity_score"
        assert "failure_category:tool_input_validation" in top_match.matched_features
        assert len(top_match.match_reason) > 0
        assert len(top_match.why_relevant or "") > 0

    def test_retrieve_empty_history(self) -> None:
        query_inc = _make_sample_incident()
        matches = retrieve_similar_incidents(query=query_inc, candidates=[])
        assert matches == []

    def test_retrieve_from_successful_run_bundle_returns_empty(self) -> None:
        bundle = RunBundle(
            scenario_id="success",
            run=RunRecord(run_id="run-succ", status="succeeded"),
            deviation=DeviationRecord(run_id="run-succ", found=False),
        )
        cand = _make_sample_incident()
        matches = retrieve_similar_incidents(query=bundle, candidates=[cand])
        assert matches == []

    def test_deterministic_tie_breaking(self) -> None:
        # Create 3 identical candidates with different IDs
        cands = [
            _make_sample_incident(
                incident_id="inc-zebra",
                category=FailureCategory.TOOL_INPUT_VALIDATION,
                pattern="path_traversal",
            ),
            _make_sample_incident(
                incident_id="inc-alpha",
                category=FailureCategory.TOOL_INPUT_VALIDATION,
                pattern="path_traversal",
            ),
            _make_sample_incident(
                incident_id="inc-beta",
                category=FailureCategory.TOOL_INPUT_VALIDATION,
                pattern="path_traversal",
            ),
        ]
        query_inc = _make_sample_incident(
            incident_id="inc-query",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            pattern="path_traversal",
        )

        matches = retrieve_similar_incidents(
            query=query_inc,
            candidates=cands,
            top_k=3,
        )

        # All scores are equal; must be sorted alphabetically by incident_id: alpha, beta, zebra
        assert len(matches) == 3
        assert matches[0].incident_id == "inc-alpha"
        assert matches[1].incident_id == "inc-beta"
        assert matches[2].incident_id == "inc-zebra"

    def test_unrelated_incidents_filtered_or_low_score(self) -> None:
        query_inc = _make_sample_incident(
            incident_id="inc-q",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            pattern="path_traversal_blocked",
        )
        unrelated = IncidentRecord(
            incident_id="inc-unrelated",
            task_summary="Deploy production network gateway",
            observed_pattern="dns_resolution_timeout",
            expected_behavior="DNS answers within 50ms",
            observed_behavior="Socket timeout on external host",
            failure_category=FailureCategory.EXTERNAL_TOOL_OR_ENVIRONMENT,
            label_status=LabelStatus.SUSPECTED,
        )

        score, features, reason, why = calculate_incident_similarity(
            query_record=query_inc,
            candidate=unrelated,
        )
        # Should have very low or 0 score
        assert score < 0.15


