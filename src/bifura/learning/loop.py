"""Verified learning loop connecting diagnosis, storage, retrieval, prediction, and verification."""

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from bifura.learning.diagnosis import diagnose_run_bundle
from bifura.learning.prediction import predict_failure
from bifura.learning.storage import IncidentStore
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    IncidentMatch,
    IncidentRecord,
    LabelStatus,
    PredictionResult,
    VerificationReport,
    utc_now,
)


def enrich_run_bundle(
    bundle: RunBundle,
    store: IncidentStore,
    persist_incident: bool = True,
    min_confidence: float = 0.35,
    top_k_matches: int = 5,
    clock: Callable[[], datetime] | None = None,
    id_generator: Callable[[], str] | None = None,
) -> RunBundle:
    """Take a RunBundle whose incident/prediction fields may be null and return the enriched bundle.

    1. Diagnoses incident from complete bundle evidence (returns None if run succeeded).
    2. Retrieves historical incidents from store.
    3. Produces evidence-backed prediction and similar matches.
    4. Optionally persists the diagnosed incident in store.
    5. Returns an enriched RunBundle with incident_records, incident_matches, and prediction.
    """
    diagnosed = diagnose_run_bundle(bundle, id_generator=id_generator, clock=clock)

    # All historical incidents currently in store
    historical_candidates = store.list_incidents()

    if diagnosed is None:
        # Successful run: no incident diagnosed
        pred, matches = predict_failure(
            query=bundle,
            historical_incidents=historical_candidates,
            min_confidence=min_confidence,
            top_k_matches=top_k_matches,
            clock=clock,
            id_generator=id_generator,
        )
        return bundle.model_copy(
            update={
                "incident_records": None,
                "incident_matches": matches,
                "prediction": pred,
            }
        )

    # Exclude the current incident ID if it was already in store to prevent self-matching
    candidates_for_query = [
        c for c in historical_candidates if c.incident_id != diagnosed.incident_id
    ]

    pred, matches = predict_failure(
        query=diagnosed,
        historical_incidents=candidates_for_query,
        min_confidence=min_confidence,
        top_k_matches=top_k_matches,
        clock=clock,
        id_generator=id_generator,
    )

    if persist_incident:
        existing = store.get_incident(diagnosed.incident_id)
        if existing is None:
            store.add_incident(diagnosed)

    return bundle.model_copy(
        update={
            "incident_records": [diagnosed],
            "incident_matches": matches,
            "prediction": pred,
        }
    )


def record_verification(
    incident_id: str,
    verification: VerificationReport,
    store: IncidentStore,
    verified_root_cause: str | None = None,
    verified_correction: str | None = None,
) -> IncidentRecord:
    """Record verified replay or test outcome on an incident record in the store.

    Honesty Invariant:
    A proposed correction is NEVER a verified correction.
    Only when verification.passed is True do we update label_status to VERIFIED
    and set training_eligible=True. If replay failed or was not run, verified fields remain unset.
    """
    incident = store.get_incident(incident_id)
    if incident is None:
        raise KeyError(f"Incident with ID '{incident_id}' not found in store.")

    if verification.passed:
        root_cause = (
            verified_root_cause
            or f"Root cause verified by passing verification report {verification.report_id or verification.verification_id or 'rep-001'}."
        )
        correction = (
            verified_correction
            or verification.summary
            or "Verified correction validated through deterministic replay."
        )

        updated = incident.model_copy(
            update={
                "label_status": LabelStatus.VERIFIED,
                "root_cause_status": "verified",
                "verified_root_cause": root_cause,
                "verified_correction": correction,
                "training_eligible": True,
                "training_eligibility": "eligible",
                "review_status": "verified",
                "replay_status": "verified_passed",
                "reviewed_at": verification.tested_at,
            }
        )
    else:
        # Replay failed: do not claim verified
        updated = incident.model_copy(
            update={
                "label_status": LabelStatus.SUSPECTED,
                "root_cause_status": "suspected",
                "verified_root_cause": None,
                "verified_correction": None,
                "training_eligible": False,
                "training_eligibility": "pending_review",
                "replay_status": "failed",
            }
        )

    store.update_incident(updated)
    return updated


def load_incident_catalog(
    catalog_path: str | Path,
    store: IncidentStore,
) -> list[IncidentRecord]:
    """Load static incident records from a JSON catalog into the IncidentStore."""
    path = Path(catalog_path)
    if not path.exists():
        raise FileNotFoundError(f"Catalog file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records: list[IncidentRecord] = []
    items = data if isinstance(data, list) else data.get("incidents", [])

    for item in items:
        rec = IncidentRecord.model_validate(item)
        existing = store.get_incident(rec.incident_id)
        if existing is None:
            store.add_incident(rec)
        records.append(rec)

    return records
