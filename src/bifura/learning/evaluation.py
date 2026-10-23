"""Evaluation module for structured retrieval and failure prediction.

Computes classification metrics, variation recognition, and harmless false-positive rates
on held-out synthetic benchmark cases.
"""

import json
from pathlib import Path
from typing import Any

from bifura.learning.prediction import predict_failure
from bifura.learning.storage import IncidentStore
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import FailureCategory, IncidentRecord


def evaluate_retrieval_classifier(
    training_data_path: str | Path = "data/datasets/training_incidents.json",
    benchmark_cases_path: str | Path = "data/evaluation/benchmark_cases.json",
    min_confidence: float = 0.35,
) -> dict[str, Any]:
    """Evaluate structured incident retrieval and prediction on held-out synthetic test cases.

    NOTICE: All benchmark data is synthetic. These metrics evaluate deterministic model logic
    and pipeline correctness; they do NOT demonstrate real-world deployment accuracy.
    """
    # 1. Load training data into an in-memory SQLite store
    store = IncidentStore(db_path=":memory:")
    with open(training_data_path, "r", encoding="utf-8") as f:
        training_records = json.load(f)

    for item in training_records:
        rec = IncidentRecord.model_validate(item)
        store.add_incident(rec)

    historical_cands = store.list_incidents()

    # 2. Load held-out benchmark cases
    with open(benchmark_cases_path, "r", encoding="utf-8") as f:
        benchmark_cases = json.load(f)

    total_cases = len(benchmark_cases)
    failure_cases = 0
    correct_failure_predictions = 0
    harmless_cases = 0
    false_positives = 0
    case_results: list[dict[str, Any]] = []

    category_stats: dict[str, dict[str, int]] = {}

    for case in benchmark_cases:
        case_id = case["case_id"]
        is_harmless = case.get("is_harmless", False)
        expected_cat = case.get("expected_category")
        bundle_data = case["bundle"]
        bundle = RunBundle.model_validate(bundle_data)

        # Predict using structured retrieval
        pred, matches = predict_failure(
            query=bundle,
            historical_incidents=historical_cands,
            min_confidence=min_confidence,
        )

        pred_cat = pred.predicted_categories[0] if pred.predicted_categories else None

        if is_harmless:
            harmless_cases += 1
            # For a harmless case, predicting any failure is a false positive
            is_fp = not pred.abstained or pred_cat is not None
            if is_fp:
                false_positives += 1
            case_results.append(
                {
                    "case_id": case_id,
                    "is_harmless": True,
                    "abstained": pred.abstained,
                    "false_positive": is_fp,
                    "predicted_category": pred_cat,
                }
            )
        else:
            failure_cases += 1
            is_correct = (not pred.abstained) and (pred_cat == expected_cat)
            if is_correct:
                correct_failure_predictions += 1

            # Track category stats
            if expected_cat:
                if expected_cat not in category_stats:
                    category_stats[expected_cat] = {"tp": 0, "fn": 0, "fp": 0}
                if is_correct:
                    category_stats[expected_cat]["tp"] += 1
                else:
                    category_stats[expected_cat]["fn"] += 1

            if pred_cat and pred_cat != expected_cat:
                if pred_cat not in category_stats:
                    category_stats[pred_cat] = {"tp": 0, "fn": 0, "fp": 0}
                category_stats[pred_cat]["fp"] += 1

            case_results.append(
                {
                    "case_id": case_id,
                    "is_harmless": False,
                    "expected_category": expected_cat,
                    "predicted_category": pred_cat,
                    "correct": is_correct,
                    "abstained": pred.abstained,
                    "top_similarity_score": matches[0].similarity_score if matches else 0.0,
                }
            )

    accuracy = (
        (correct_failure_predictions / failure_cases)
        if failure_cases > 0
        else 1.0
    )
    fp_rate = (false_positives / harmless_cases) if harmless_cases > 0 else 0.0

    # Macro-F1 calculation across failure categories
    f1_scores: list[float] = []
    per_category: dict[str, dict[str, float]] = {}

    for cat, stats in category_stats.items():
        tp = stats["tp"]
        fp = stats["fp"]
        fn = stats["fn"]
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            (2 * precision * recall) / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )
        f1_scores.append(f1)
        per_category[cat] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp + fn,
        }

    macro_f1 = sum(f1_scores) / len(f1_scores) if f1_scores else 1.0

    return {
        "evaluation_dataset": "synthetic_controlled_benchmark",
        "is_synthetic": True,
        "disclaimer": (
            "NOTICE: Results are measured on synthetic test fixtures for pipeline verification; "
            "they do NOT represent real-world performance."
        ),
        "total_cases": total_cases,
        "failure_cases": failure_cases,
        "harmless_cases": harmless_cases,
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "false_positive_count": false_positives,
        "false_positive_rate": round(fp_rate, 4),
        "per_category_metrics": per_category,
        "case_details": case_results,
    }
