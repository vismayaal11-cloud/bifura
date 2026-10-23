"""Deterministic, explainable structured similarity retrieval for Bifura incidents."""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from bifura.learning.diagnosis import diagnose_run_bundle
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    FailureCategory,
    IncidentMatch,
    IncidentRecord,
    LabelStatus,
    utc_now,
)

# Standard tools recognized in Bifura practice runs
KNOWN_TOOLS = {"read_file", "write_file", "calculate"}

STOP_WORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "is", "was", "were", "be", "been", "that", "this", "from", "as", "it",
    "its", "are", "not", "test", "run", "agent", "task",
}

SCORING_FORMULA_DOC = (
    "similarity_score = 0.35 * category_match + 0.25 * pattern_match + "
    "0.20 * tool_match + 0.20 * text_jaccard"
)


def _tokenize(text: str | None) -> set[str]:
    """Tokenize and filter stop words from text."""
    if not text:
        return set()
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return {t for t in tokens if len(t) > 1 and t not in STOP_WORDS}


def _extract_tools(text: str | None) -> set[str]:
    """Extract recognized tool names from text or field contents."""
    if not text:
        return set()
    tokens = _tokenize(text)
    return tokens.intersection(KNOWN_TOOLS)


def calculate_incident_similarity(
    query_record: IncidentRecord,
    candidate: IncidentRecord,
) -> tuple[float, list[str], str, str]:
    """Calculate structured similarity between query incident and a candidate.

    Returns:
        (similarity_score, matched_features, match_reason, why_relevant)
    """
    matched_features: list[str] = []

    # 1. Category match (weight 0.35)
    cat_score = 0.0
    if (
        query_record.failure_category != FailureCategory.UNKNOWN_INSUFFICIENT_EVIDENCE
        and query_record.failure_category == candidate.failure_category
    ):
        cat_score = 1.0
        matched_features.append(f"failure_category:{candidate.failure_category.value}")

    # 2. Observed pattern match (weight 0.25)
    pattern_score = 0.0
    if query_record.observed_pattern and candidate.observed_pattern:
        if query_record.observed_pattern == candidate.observed_pattern:
            pattern_score = 1.0
            matched_features.append(f"pattern:{candidate.observed_pattern}")
        else:
            q_pat_tokens = _tokenize(query_record.observed_pattern)
            c_pat_tokens = _tokenize(candidate.observed_pattern)
            if q_pat_tokens and c_pat_tokens:
                p_jaccard = len(q_pat_tokens & c_pat_tokens) / len(q_pat_tokens | c_pat_tokens)
                if p_jaccard > 0.0:
                    pattern_score = p_jaccard
                    matched_features.append("partial_pattern_overlap")

    # 3. Tool / action match (weight 0.20)
    q_tools = _extract_tools(
        f"{query_record.task_summary} {query_record.observed_behavior} {query_record.observed_pattern}"
    )
    c_tools = _extract_tools(
        f"{candidate.task_summary} {candidate.observed_behavior} {candidate.observed_pattern}"
    )
    tool_score = 0.0
    if q_tools and c_tools:
        shared_tools = q_tools & c_tools
        if shared_tools:
            tool_score = len(shared_tools) / len(q_tools | c_tools)
            matched_features.append(f"tool_names:{','.join(sorted(shared_tools))}")

    # 4. Context & behavioral text overlap (weight 0.20)
    q_text = " ".join(
        filter(
            None,
            [
                query_record.task_summary,
                query_record.expected_behavior,
                query_record.observed_behavior,
                query_record.root_cause_summary,
            ],
        )
    )
    c_text = " ".join(
        filter(
            None,
            [
                candidate.task_summary,
                candidate.expected_behavior,
                candidate.observed_behavior,
                candidate.root_cause_summary,
            ],
        )
    )
    q_tokens = _tokenize(q_text)
    c_tokens = _tokenize(c_text)
    text_score = 0.0
    if q_tokens and c_tokens:
        jaccard = len(q_tokens & c_tokens) / len(q_tokens | c_tokens)
        text_score = jaccard
        if jaccard >= 0.15:
            matched_features.append("context_and_behavioral_overlap")

    # Composite weighted similarity score bounded in [0.0, 1.0]
    raw_score = (
        0.35 * cat_score
        + 0.25 * pattern_score
        + 0.20 * tool_score
        + 0.20 * text_score
    )
    final_score = max(0.0, min(1.0, round(raw_score, 4)))

    match_reason = (
        f"Formula: {SCORING_FORMULA_DOC}. "
        f"Category match ({cat_score:.2f}), pattern match ({pattern_score:.2f}), "
        f"tool match ({tool_score:.2f}), text Jaccard ({text_score:.2f}). "
        f"Matched: {', '.join(matched_features) if matched_features else 'none'}."
    )

    why_relevant = (
        f"Candidate '{candidate.incident_id}' shares structural features with query "
        f"(category={candidate.failure_category.value}, pattern={candidate.observed_pattern or 'n/a'}). "
        "Similarity indicates high structural precedence; does not prove identical root cause."
    )

    return final_score, matched_features, match_reason, why_relevant


def retrieve_similar_incidents(
    query: IncidentRecord | RunBundle,
    candidates: list[IncidentRecord],
    top_k: int = 5,
    min_similarity: float = 0.10,
    clock: Callable[[], datetime] | None = None,
    id_generator: Callable[[], str] | None = None,
) -> list[IncidentMatch]:
    """Retrieve and rank similar incidents from historical incident records.

    Enforces deterministic tie-breaking (by score descending, then incident_id ascending).
    Follows canonical IncidentMatch schema without modifying shared models.
    """
    if isinstance(query, RunBundle):
        query_record = diagnose_run_bundle(query)
        if query_record is None:
            # Successful run without deviation has no failure to match
            return []
        run_id = query.run.run_id
    else:
        query_record = query
        run_id = query.run_id

    if not candidates:
        return []

    now = clock() if clock is not None else utc_now()
    matches: list[IncidentMatch] = []

    for cand in candidates:
        score, features, reason, why = calculate_incident_similarity(
            query_record=query_record,
            candidate=cand,
        )

        if score < min_similarity:
            continue

        match_id = (
            id_generator()
            if id_generator is not None
            else f"match-{query_record.incident_id}-{cand.incident_id}"
        )

        is_verified = (
            cand.label_status == LabelStatus.VERIFIED
            or cand.root_cause_status == "verified"
            or cand.replay_status == "verified_passed"
        )

        matches.append(
            IncidentMatch(
                incident_id=cand.incident_id,
                match_id=match_id,
                run_id=run_id,
                similarity_score=score,
                score_kind="similarity_score",
                match_reason=reason,
                why_relevant=why,
                matched_features=features,
                verified=is_verified,
                retrieved_at=now,
            )
        )

    # Deterministic tie-breaking: highest score first, then alphabetical incident_id
    matches.sort(key=lambda m: (-m.similarity_score, m.incident_id))

    return matches[:top_k]
