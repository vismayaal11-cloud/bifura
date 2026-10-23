"""SQLite-backed incident memory store for Bifura learning assets."""

import json
import sqlite3
from pathlib import Path
from typing import Any

from bifura.schemas.models import (
    FailureCategory,
    IncidentRecord,
    LabelStatus,
)


class DuplicateIncidentError(ValueError):
    """Raised when attempting to store an incident with an existing incident_id."""


class IncidentStore:
    """Persistent and queryable SQLite storage for canonical IncidentRecords.

    Validates records back into canonical Pydantic IncidentRecord models on retrieval.
    Enforces Bifura honesty rules (e.g., suspected incidents cannot be training_eligible).
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS incidents (
                    incident_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    source_run_id TEXT,
                    failure_category TEXT NOT NULL,
                    label_status TEXT NOT NULL,
                    observed_pattern TEXT,
                    first_deviation_event_id TEXT,
                    training_eligible INTEGER NOT NULL,
                    replay_status TEXT,
                    dataset_version TEXT,
                    data_origin TEXT,
                    provenance TEXT,
                    created_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(failure_category);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incidents_run_id ON incidents(run_id);"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incidents_training_eligible ON incidents(training_eligible);"
            )

    def _validate_honesty(self, record: IncidentRecord) -> None:
        """Enforce Bifura honesty rules on incident records."""
        if record.label_status == LabelStatus.SUSPECTED and record.training_eligible:
            raise ValueError(
                f"Honesty violation: Incident {record.incident_id} has label_status='suspected' "
                "and cannot be marked training_eligible=True."
            )

    def add_incident(self, record: IncidentRecord) -> None:
        """Store a new IncidentRecord.

        Raises DuplicateIncidentError if an incident with the same ID exists.
        Raises ValueError if honesty invariants are violated.
        """
        self._validate_honesty(record)
        record_json = record.model_dump_json()

        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO incidents (
                        incident_id,
                        run_id,
                        source_run_id,
                        failure_category,
                        label_status,
                        observed_pattern,
                        first_deviation_event_id,
                        training_eligible,
                        replay_status,
                        dataset_version,
                        data_origin,
                        provenance,
                        created_at,
                        record_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.incident_id,
                        record.run_id,
                        record.source_run_id,
                        record.failure_category.value
                        if isinstance(record.failure_category, FailureCategory)
                        else str(record.failure_category),
                        record.label_status.value
                        if isinstance(record.label_status, LabelStatus)
                        else str(record.label_status),
                        record.observed_pattern,
                        record.first_deviation_event_id,
                        1 if record.training_eligible else 0,
                        record.replay_status,
                        record.dataset_version,
                        record.data_origin,
                        record.provenance,
                        record.created_at.isoformat(),
                        record_json,
                    ),
                )
            except sqlite3.IntegrityError as err:
                raise DuplicateIncidentError(
                    f"Incident with ID '{record.incident_id}' already exists."
                ) from err

    def get_incident(self, incident_id: str) -> IncidentRecord | None:
        """Retrieve an IncidentRecord by its ID and validate into canonical model."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT record_json FROM incidents WHERE incident_id = ?",
                (incident_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            data = json.loads(row["record_json"])
            return IncidentRecord.model_validate(data)

    def update_incident(self, record: IncidentRecord) -> None:
        """Update an existing IncidentRecord."""
        self._validate_honesty(record)
        record_json = record.model_dump_json()

        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE incidents SET
                    run_id = ?,
                    source_run_id = ?,
                    failure_category = ?,
                    label_status = ?,
                    observed_pattern = ?,
                    first_deviation_event_id = ?,
                    training_eligible = ?,
                    replay_status = ?,
                    dataset_version = ?,
                    data_origin = ?,
                    provenance = ?,
                    record_json = ?
                WHERE incident_id = ?
                """,
                (
                    record.run_id,
                    record.source_run_id,
                    record.failure_category.value
                    if isinstance(record.failure_category, FailureCategory)
                    else str(record.failure_category),
                    record.label_status.value
                    if isinstance(record.label_status, LabelStatus)
                    else str(record.label_status),
                    record.observed_pattern,
                    record.first_deviation_event_id,
                    1 if record.training_eligible else 0,
                    record.replay_status,
                    record.dataset_version,
                    record.data_origin,
                    record.provenance,
                    record_json,
                    record.incident_id,
                ),
            )
            if cur.rowcount == 0:
                raise KeyError(f"Incident with ID '{record.incident_id}' not found.")

    def list_incidents(
        self,
        failure_category: FailureCategory | str | None = None,
        training_eligible_only: bool = False,
        limit: int | None = None,
    ) -> list[IncidentRecord]:
        """List and filter incidents, validating each into an IncidentRecord model."""
        query = "SELECT record_json FROM incidents WHERE 1=1"
        params: list[Any] = []

        if failure_category is not None:
            cat_val = (
                failure_category.value
                if isinstance(failure_category, FailureCategory)
                else str(failure_category)
            )
            query += " AND failure_category = ?"
            params.append(cat_val)

        if training_eligible_only:
            query += " AND training_eligible = 1"

        query += " ORDER BY created_at DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            return [
                IncidentRecord.model_validate(json.loads(r["record_json"]))
                for r in rows
            ]

    def count_incidents(self) -> int:
        """Return total number of incidents stored."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) AS cnt FROM incidents")
            return int(cur.fetchone()["cnt"])
