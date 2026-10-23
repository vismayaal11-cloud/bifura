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
    PredictionResult,
    RunRecord,
    TraceEvent,
    VerificationReport,
)
from bifura.schemas.bundle import RunBundle
from bifura.learning import (
    DuplicateIncidentError,
    HEURISTIC_SCORE_MEANING,
    IncidentStore,
    calculate_incident_similarity,
    diagnose_run_bundle,
    enrich_run_bundle,
    evaluate_retrieval_classifier,
    load_incident_catalog,
    predict_failure,
    record_verification,
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


class TestPrediction:
    """Test suite for evidence-based prediction (Critical Step 4)."""

    def test_predict_failure_with_strong_historical_evidence(self) -> None:
        query_inc = _make_sample_incident(
            incident_id="inc-q1",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            pattern="path_traversal_blocked",
        )
        cand1 = _make_sample_incident(
            incident_id="inc-cand1",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            pattern="path_traversal_blocked",
        )
        cand2 = _make_sample_incident(
            incident_id="inc-cand2",
            category=FailureCategory.STATE_OR_DATAFLOW,
            pattern="stale_state",
        )

        pred, matches = predict_failure(
            query=query_inc,
            historical_incidents=[cand1, cand2],
            min_confidence=0.35,
        )

        assert pred.abstained is False
        assert pred.abstention_reason is None
        assert pred.predicted_categories == ["tool_input_validation"]
        assert pred.score_meaning == "heuristic_support_score"
        assert pred.prediction_mode == "structured_retrieval"
        assert "inc-cand1" in pred.supporting_incident_ids
        assert len(pred.candidates) >= 1
        assert pred.candidates[0]["category"] == "tool_input_validation"
        assert pred.candidates[0]["score_kind"] == "heuristic_support_score"
        assert pred.scores["tool_input_validation"] > 0.50

    def test_predict_failure_abstains_on_empty_history(self) -> None:
        query_inc = _make_sample_incident()
        pred, matches = predict_failure(
            query=query_inc,
            historical_incidents=[],
        )

        assert pred.abstained is True
        assert "No historical incident records available" in (
            pred.abstention_reason or ""
        )
        assert pred.predicted_categories == []
        assert pred.supporting_incident_ids == []
        assert pred.score_meaning == "heuristic_support_score"
        assert pred.prediction_mode == "structured_retrieval"

    def test_predict_failure_abstains_on_low_confidence(self) -> None:
        query_inc = _make_sample_incident(
            incident_id="inc-q",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            pattern="path_traversal_blocked",
        )
        # Category matches (gives ~0.35), but min_confidence requires 0.60
        cand = IncidentRecord(
            incident_id="inc-cat-only",
            task_summary="Unrelated database backup",
            observed_pattern="schema_syntax_error",
            failure_category=FailureCategory.TOOL_INPUT_VALIDATION,
            label_status=LabelStatus.SUSPECTED,
        )

        pred, matches = predict_failure(
            query=query_inc,
            historical_incidents=[cand],
            min_confidence=0.60,  # Require at least 0.60 confidence
        )

        assert pred.abstained is True
        assert "below minimum confidence threshold" in (
            pred.abstention_reason or ""
        )
        assert pred.predicted_categories == []

    def test_predict_failure_abstains_on_successful_bundle(self) -> None:
        bundle = RunBundle(
            scenario_id="success",
            run=RunRecord(run_id="run-succ", status="succeeded"),
            deviation=DeviationRecord(run_id="run-succ", found=False),
        )
        cand = _make_sample_incident()

        pred, matches = predict_failure(
            query=bundle,
            historical_incidents=[cand],
        )

        assert pred.abstained is True
        assert "No deviation observed" in (pred.abstention_reason or "")
        assert pred.predicted_categories == []

    def test_predict_failure_deterministic_injection(self) -> None:
        fixed_dt = datetime(2026, 10, 23, 15, 30, 0, tzinfo=timezone.utc)
        query_inc = _make_sample_incident()
        cand = _make_sample_incident(incident_id="inc-cand")

        pred, matches = predict_failure(
            query=query_inc,
            historical_incidents=[cand],
            clock=lambda: fixed_dt,
            id_generator=lambda: "pred-fixed-test-id",
        )

        assert pred.prediction_id == "pred-fixed-test-id"
        assert pred.created_at == fixed_dt


class TestLearningLoop:
    """Test suite for verified learning loop (Critical Step 5)."""

    def test_enrich_run_bundle_with_null_learning_fields(
        self, tmp_path: Path
    ) -> None:
        db_file = tmp_path / "learning_loop.db"
        store = IncidentStore(db_path=db_file)

        # Seed store with historical verified incident
        hist_inc = _make_sample_incident(
            incident_id="inc-hist-001",
            category=FailureCategory.TOOL_INPUT_VALIDATION,
            pattern="path_traversal_blocked",
            label_status=LabelStatus.VERIFIED,
            training_eligible=True,
        )
        store.add_incident(hist_inc)

        # Bundle with null learning fields
        bundle = RunBundle(
            scenario_id="wrong_path",
            run=RunRecord(run_id="run-new-001", status="blocked"),
            deviation=DeviationRecord(
                run_id="run-new-001",
                found=True,
                first_deviation_event_id="ev-001",
                description="Path traversal attempt blocked by safety policy",
            ),
            incident_records=None,
            incident_matches=None,
            prediction=None,
        )

        enriched = enrich_run_bundle(
            bundle=bundle,
            store=store,
            persist_incident=True,
        )

        assert enriched.incident_records is not None
        assert len(enriched.incident_records) == 1
        assert (
            enriched.incident_records[0].failure_category
            == FailureCategory.TOOL_INPUT_VALIDATION
        )

        assert enriched.incident_matches is not None
        assert len(enriched.incident_matches) >= 1
        assert enriched.incident_matches[0].incident_id == "inc-hist-001"

        assert enriched.prediction is not None
        assert enriched.prediction.abstained is False
        assert enriched.prediction.predicted_categories == [
            "tool_input_validation"
        ]
        assert enriched.prediction.score_meaning == "heuristic_support_score"

        # Check it was persisted in store
        persisted = store.get_incident(enriched.incident_records[0].incident_id)
        assert persisted is not None

    def test_record_verification_success_enables_training(
        self, tmp_path: Path
    ) -> None:
        db_file = tmp_path / "verification.db"
        store = IncidentStore(db_path=db_file)

        incident = _make_sample_incident(
            incident_id="inc-unverified-001",
            label_status=LabelStatus.SUSPECTED,
            training_eligible=False,
        )
        store.add_incident(incident)

        report = VerificationReport(
            report_id="rep-001",
            verification_id="ver-001",
            run_id="run-replay-001",
            passed=True,
            summary="Replay passed after path normalization patch.",
            replay_status="passed",
        )

        updated = record_verification(
            incident_id="inc-unverified-001",
            verification=report,
            store=store,
            verified_root_cause="Path resolution logic bypassed sandbox containment.",
            verified_correction="Strict path resolution inside sandbox_root.",
        )

        assert updated.label_status == LabelStatus.VERIFIED
        assert updated.training_eligible is True
        assert updated.replay_status == "verified_passed"
        assert updated.verified_root_cause is not None
        assert updated.verified_correction is not None

        # Verify it can be retrieved as training_eligible
        eligible = store.list_incidents(training_eligible_only=True)
        assert len(eligible) == 1
        assert eligible[0].incident_id == "inc-unverified-001"

    def test_record_verification_failure_leaves_unverified(
        self, tmp_path: Path
    ) -> None:
        db_file = tmp_path / "verification_fail.db"
        store = IncidentStore(db_path=db_file)

        incident = _make_sample_incident(
            incident_id="inc-failed-replay",
            label_status=LabelStatus.SUSPECTED,
            training_eligible=False,
        )
        store.add_incident(incident)

        failed_report = VerificationReport(
            report_id="rep-fail-001",
            passed=False,
            summary="Candidate patch failed replay assertions.",
        )

        updated = record_verification(
            incident_id="inc-failed-replay",
            verification=failed_report,
            store=store,
        )

        assert updated.label_status != LabelStatus.VERIFIED
        assert updated.training_eligible is False
        assert updated.verified_root_cause is None
        assert updated.verified_correction is None

    def test_load_incident_catalog_fixtures(self, tmp_path: Path) -> None:
        db_file = tmp_path / "catalog.db"
        store = IncidentStore(db_path=db_file)

        records = load_incident_catalog(
            catalog_path="data/incidents/catalog.json",
            store=store,
        )

        assert len(records) >= 3
        assert store.count_incidents() >= 3

        # Confirm provenance is synthetic_fixture
        for rec in records:
            assert rec.provenance == "synthetic_fixture"
            assert rec.data_origin == "controlled_fixture"
            assert (
                rec.incident_id.startswith("syn-inc-")
            )


class TestEvaluation:
    """Test suite for evaluation dataset and metrics (Optional Step 6)."""

    def test_evaluate_retrieval_classifier_metrics(self) -> None:
        report = evaluate_retrieval_classifier(
            training_data_path="data/datasets/training_incidents.json",
            benchmark_cases_path="data/evaluation/benchmark_cases.json",
            min_confidence=0.35,
        )

        assert report["is_synthetic"] is True
        assert "NOTICE" in report["disclaimer"]
        assert report["total_cases"] == 4
        assert report["failure_cases"] == 3
        assert report["harmless_cases"] == 1

        # Harmless case must not produce a false positive failure prediction
        assert report["false_positive_count"] == 0
        assert report["false_positive_rate"] == 0.0

        # All 3 failure cases should be correctly predicted by structured similarity
        assert report["accuracy"] == 1.0
        assert report["macro_f1"] == 1.0

        # Check per-category breakdowns
        per_cat = report["per_category_metrics"]
        assert "tool_input_validation" in per_cat
        assert "state_or_dataflow" in per_cat
        assert "planning_or_tool_sequence" in per_cat

