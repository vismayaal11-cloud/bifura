"""Evidence-based failure prediction using structured retrieval from incident memory."""

from collections.abc import Callable
from datetime import datetime
from typing import Any

from bifura.learning.diagnosis import diagnose_run_bundle
from bifura.learning.retrieval import retrieve_similar_incidents
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    FailureCategory,
    IncidentMatch,
    IncidentRecord,
    PredictionResult,
    utc_now,
)

PREDICTION_MODEL_VERSION = "heuristic-retrieval-v1"
PREDICTION_DATASET_VERSION = "dataset-v1"
PREDICTION_MODE = "structured_retrieval"
HEURISTIC_SCORE_MEANING = "heuristic_support_score"


def predict_failure(
    query: RunBundle | IncidentRecord,
    historical_incidents: list[IncidentRecord],
    min_confidence: float = 0.35,
    top_k_matches: int = 5,
    clock: Callable[[], datetime] | None = None,
    id_generator: Callable[[], str] | None = None,
) -> tuple[PredictionResult, list[IncidentMatch]]:
    """Generate an evidence-backed PredictionResult and supporting matches from historical incidents.

    Abstains honestly when:
    - The current run has no deviation (success)
    - Historical incidents store is empty
    - No retrieved matches exceed the similarity threshold
    - Top match score is below min_confidence threshold

    Returns:
        (PredictionResult, list[IncidentMatch])
    """
    now = clock() if clock is not None else utc_now()

    # Determine run_id and query record
    if isinstance(query, RunBundle):
        run_id = query.run.run_id
        if query.deviation is None or not query.deviation.found:
            pred_id = id_generator() if id_generator is not None else f"pred-{run_id}"
            return (
                PredictionResult(
                    run_id=run_id,
                    prediction_id=pred_id,
                    model_version=PREDICTION_MODEL_VERSION,
                    dataset_version=PREDICTION_DATASET_VERSION,
                    prediction_mode=PREDICTION_MODE,
                    predicted_categories=[],
                    candidates=[],
                    scores={},
                    score_meaning=HEURISTIC_SCORE_MEANING,
                    abstained=True,
                    abstention_reason="No deviation observed in current run; prediction not required.",
                    supporting_incident_ids=[],
                    created_at=now,
                ),
                [],
            )
        query_record = diagnose_run_bundle(query, clock=clock)
        if query_record is None:
            pred_id = id_generator() if id_generator is not None else f"pred-{run_id}"
            return (
                PredictionResult(
                    run_id=run_id,
                    prediction_id=pred_id,
                    model_version=PREDICTION_MODEL_VERSION,
                    dataset_version=PREDICTION_DATASET_VERSION,
                    prediction_mode=PREDICTION_MODE,
                    predicted_categories=[],
                    candidates=[],
                    scores={},
                    score_meaning=HEURISTIC_SCORE_MEANING,
                    abstained=True,
                    abstention_reason="Diagnosis produced no incident record from bundle evidence.",
                    supporting_incident_ids=[],
                    created_at=now,
                ),
                [],
            )
    else:
        query_record = query
        run_id = query.run_id or "run-unknown"

    pred_id = id_generator() if id_generator is not None else f"pred-{run_id}"

    # Handle empty historical incident catalog
    if not historical_incidents:
        return (
            PredictionResult(
                run_id=run_id,
                prediction_id=pred_id,
                model_version=PREDICTION_MODEL_VERSION,
                dataset_version=PREDICTION_DATASET_VERSION,
                prediction_mode=PREDICTION_MODE,
                predicted_categories=[],
                candidates=[],
                scores={},
                score_meaning=HEURISTIC_SCORE_MEANING,
                abstained=True,
                abstention_reason="No historical incident records available in store for evidence-based prediction.",
                supporting_incident_ids=[],
                created_at=now,
            ),
            [],
        )

    # Retrieve similar incidents
    matches = retrieve_similar_incidents(
        query=query_record,
        candidates=historical_incidents,
        top_k=top_k_matches,
        min_similarity=0.10,
        clock=clock,
        id_generator=id_generator,
    )

    if not matches:
        return (
            PredictionResult(
                run_id=run_id,
                prediction_id=pred_id,
                model_version=PREDICTION_MODEL_VERSION,
                dataset_version=PREDICTION_DATASET_VERSION,
                prediction_mode=PREDICTION_MODE,
                predicted_categories=[],
                candidates=[],
                scores={},
                score_meaning=HEURISTIC_SCORE_MEANING,
                abstained=True,
                abstention_reason="No similar historical incidents met the minimum similarity threshold.",
                supporting_incident_ids=[],
                created_at=now,
            ),
            [],
        )

    # Check top similarity score against min_confidence threshold
    top_score = matches[0].similarity_score
    if top_score < min_confidence:
        return (
            PredictionResult(
                run_id=run_id,
                prediction_id=pred_id,
                model_version=PREDICTION_MODEL_VERSION,
                dataset_version=PREDICTION_DATASET_VERSION,
                prediction_mode=PREDICTION_MODE,
                predicted_categories=[],
                candidates=[],
                scores={},
                score_meaning=HEURISTIC_SCORE_MEANING,
                abstained=True,
                abstention_reason=(
                    f"Highest retrieved similarity score ({top_score:.2f}) is below "
                    f"minimum confidence threshold ({min_confidence:.2f})."
                ),
                supporting_incident_ids=[m.incident_id for m in matches],
                created_at=now,
            ),
            matches,
        )

    # Map candidate records for category attribution
    cand_by_id = {c.incident_id: c for c in historical_incidents}

    # Aggregate candidate scores by failure category
    cat_scores: dict[str, float] = {}
    cat_supporting_ids: dict[str, list[str]] = {}

    for m in matches:
        cand = cand_by_id.get(m.incident_id)
        if cand is None:
            continue
        cat_str = (
            cand.failure_category.value
            if isinstance(cand.failure_category, FailureCategory)
            else str(cand.failure_category)
        )
        if cat_str not in cat_scores or m.similarity_score > cat_scores[cat_str]:
            cat_scores[cat_str] = m.similarity_score

        if cat_str not in cat_supporting_ids:
            cat_supporting_ids[cat_str] = []
        cat_supporting_ids[cat_str].append(m.incident_id)

    # Sort categories deterministically: descending score, then category name
    sorted_cats = sorted(cat_scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_category = sorted_cats[0][0]
    supporting_ids = cat_supporting_ids.get(top_category, [])

    candidates_list: list[dict[str, Any]] = [
        {
            "category": cat,
            "score": score,
            "score_kind": HEURISTIC_SCORE_MEANING,
        }
        for cat, score in sorted_cats
    ]

    return (
        PredictionResult(
            run_id=run_id,
            prediction_id=pred_id,
            model_version=PREDICTION_MODEL_VERSION,
            dataset_version=PREDICTION_DATASET_VERSION,
            prediction_mode=PREDICTION_MODE,
            predicted_categories=[top_category],
            candidates=candidates_list,
            scores=dict(sorted_cats),
            score_meaning=HEURISTIC_SCORE_MEANING,
            abstained=False,
            abstention_reason=None,
            supporting_incident_ids=supporting_ids,
            created_at=now,
        ),
        matches,
    )
