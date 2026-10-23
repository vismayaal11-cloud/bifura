"""Tests for Bifura learning module: storage, diagnosis, retrieval, prediction, and learning loop."""

import pytest
from pathlib import Path
from datetime import datetime, timezone

from bifura.schemas.models import (
    FailureCategory,
    IncidentRecord,
    LabelStatus,
)
from bifura.learning.storage import (
    DuplicateIncidentError,
    IncidentStore,
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
