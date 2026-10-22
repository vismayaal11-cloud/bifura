"""Canonical Pydantic v2 data contracts for Bifura."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Contract(BaseModel):
    """Base model for all Bifura contracts.
    
    Enforces strict typing, forbids unexpected fields, and supplies the
    mandatory top-level schema_version required by the project specification.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    schema_version: str = "1.0"


# ---------------------------------------------------------------------------
# Shared Enums
# ---------------------------------------------------------------------------


class EventStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    UNKNOWN = "unknown"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"


class EventType(str, Enum):
    TASK_STARTED = "task_started"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    TOOL_PROPOSED = "tool_proposed"
    SAFETY_DECISION = "safety_decision"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_BLOCKED = "tool_blocked"
    STATE_UPDATED = "state_updated"
    ASSERTION_PASSED = "assertion_passed"
    ASSERTION_FAILED = "assertion_failed"
    ERROR = "error"
    RUN_FINISHED = "run_finished"


class ActorType(str, Enum):
    USER = "user"
    AGENT = "agent"
    LLM = "llm"
    SAFETY_ENGINE = "safety_engine"
    TOOL = "tool"
    EVALUATOR = "evaluator"
    SYSTEM = "system"


class SafetyDecisionType(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


DecisionType = SafetyDecisionType  # Canonical alias


class ExecutionStatus(str, Enum):
    NOT_STARTED = "not_started"
    AWAITING_REVIEW = "awaiting_review"
    BLOCKED_BEFORE_EXECUTION = "blocked_before_execution"
    APPROVED_NOT_EXECUTED = "approved_not_executed"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"
    CANCELLED = "cancelled"


class FailureCategory(str, Enum):
    """7 canonical failure categories agreed across Bifura specification."""

    TOOL_INPUT_VALIDATION = "tool_input_validation"
    STATE_OR_DATAFLOW = "state_or_dataflow"
    PLANNING_OR_TOOL_SEQUENCE = "planning_or_tool_sequence"
    RETRY_LOGIC = "retry_logic"
    EXTERNAL_TOOL_OR_ENVIRONMENT = "external_tool_or_environment"
    MODEL_REASONING_OR_INSTRUCTION_HANDLING = (
        "model_reasoning_or_instruction_handling"
    )
    UNKNOWN_INSUFFICIENT_EVIDENCE = "unknown_insufficient_evidence"

    # Compatibility aliases for initial prototype drafts
    STATE_PROPAGATION = "state_or_dataflow"
    PLAN_TOOL_SEQUENCE = "planning_or_tool_sequence"
    OTHER = "unknown_insufficient_evidence"
    UNKNOWN = "unknown_insufficient_evidence"


class LabelStatus(str, Enum):
    SUSPECTED = "suspected"
    REVIEWED = "reviewed"
    VERIFIED = "verified"


class HypothesisStatus(str, Enum):
    CANDIDATE = "candidate"
    SUPPORTED = "supported"
    REJECTED = "rejected"
    VERIFIED = "verified"


class EvidenceStatus(str, Enum):
    OBSERVED = "observed"
    CONFIRMED = "confirmed"
    INFERRED = "inferred"


# ---------------------------------------------------------------------------
# Execution & Trace Records
# ---------------------------------------------------------------------------


class RunRecord(Contract):
    """Execution metadata and boundary conditions for a single agent run."""

    run_id: str
    task_text: str | None = None
    task_summary: str | None = None
    expected_outcome: str | None = None
    expected_behavior: str | None = None
    actual_behavior: str | None = None
    status: RunStatus | EventStatus | str = RunStatus.PENDING
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    agent_name: str = "bifura_practice_agent"
    agent_version: str = "0.1.0"
    llm_provider: str | None = None
    llm_model: str | None = None
    is_fixture: bool = False
    reference_run_id: str | None = None
    raw_trace_ref: str | None = None
    event_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class TraceEvent(Contract):
    """An individual event recorded in the execution trace."""

    run_id: str
    event_id: str
    sequence: int = Field(ge=0)
    event_type: str
    timestamp: datetime = Field(default_factory=utc_now)
    parent_event_id: str | None = None
    actor: str = "agent"
    name: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    summary: str | None = None
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    state_delta: dict[str, Any] | None = None
    input_ref: str | None = None
    output_ref: str | None = None
    state_before_ref: str | None = None
    state_after_ref: str | None = None
    status: str = "observed"
    provenance: str = "unknown"
    error: str | None = None
    error_type: str | None = None
    depends_on_event_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    assertions: list[str] = Field(default_factory=list)
    source_location: str | None = None
    agent_node: str | None = None
    data_dependencies: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Safety & Tool Proposal Records
# ---------------------------------------------------------------------------


class ToolCallProposal(Contract):
    """Untrusted proposed tool action submitted for safety evaluation."""

    proposal_id: str
    tool_name: str
    run_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    tool_call_id: str | None = None
    proposal_event_id: str | None = None
    target: str | None = None
    purpose: str | None = None
    hypothesis_id: str | None = None
    model_generated_metadata: dict[str, Any] = Field(default_factory=dict)
    trusted_context_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


ToolProposal = ToolCallProposal  # Canonical alias


class SafetyDecisionRecord(Contract):
    """Safety policy evaluation record produced by the central policy engine."""

    decision_id: str
    decision: SafetyDecisionType
    proposal_id: str | None = None
    tool_call_id: str | None = None
    run_id: str | None = None
    policy_rule: str = "default_policy"
    rule_ids: list[str] = Field(default_factory=list)
    reason: str
    policy_version: str = "1.0"
    validated_target: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    redacted_evidence: list[str] = Field(default_factory=list)
    execution_status: ExecutionStatus = ExecutionStatus.NOT_STARTED
    review_status: str = "not_required"
    authorized_by: str | None = None
    decided_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


SafetyDecision = SafetyDecisionRecord  # Canonical alias


class ToolExecutionResult(Contract):
    """Post-execution result returned by the central executor if allowed."""

    proposal_id: str
    decision_id: str
    executed: bool
    success: bool | None = None
    result_data: dict[str, Any] | None = None
    result_ref: str | None = None
    error_type: str | None = None
    error_message: str | None = None


# ---------------------------------------------------------------------------
# Investigation, Deviation & Hypothesis Records
# ---------------------------------------------------------------------------


class DeviationRecord(Contract):
    """Observed discrepancy between expected and actual execution behavior."""

    run_id: str
    deviation_id: str | None = None
    event_id: str | None = None
    first_deviation_event_id: str | None = None
    found: bool = True
    expected: dict[str, Any] | None = None
    actual: dict[str, Any] | None = None
    expected_behavior: str | None = None
    observed_behavior: str | None = None
    description: str | None = None
    explanation: str | None = None
    first_observed_deviation: bool = True
    evidence_refs: list[str] = Field(default_factory=list)
    status: str = "observed"


DeviationResult = DeviationRecord  # Canonical alias


class HypothesisRecord(Contract):
    """A candidate explanation for an observed deviation."""

    hypothesis_id: str
    run_id: str
    candidate_cause: str | None = None
    statement: str | None = None
    failure_category: FailureCategory = (
        FailureCategory.UNKNOWN_INSUFFICIENT_EVIDENCE
    )
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    contradicting_evidence_refs: list[str] = Field(default_factory=list)
    rank: int = 1
    score: float | None = None
    score_kind: str | None = None
    status: HypothesisStatus = HypothesisStatus.CANDIDATE
    confidence_label: str = "unknown"
    confidence_source: str | None = None
    next_experiment: str | None = None
    verification_notes: str | None = None


# ---------------------------------------------------------------------------
# Graph & Dependency Records
# ---------------------------------------------------------------------------


class DependencyEdge(Contract):
    """A causal or dataflow dependency between two execution trace events."""

    from_event_id: str
    to_event_id: str
    edge_id: str | None = None
    run_id: str | None = None
    dependency_type: str = "consumes_output"
    evidence_status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence_refs: list[str] = Field(default_factory=list)
    explanation: str | None = None


class ImpactGraph(Contract):
    """Impact graph representation of an execution run."""

    run_id: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[DependencyEdge | dict[str, Any]] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Incident & Prediction Records
# ---------------------------------------------------------------------------


class IncidentRecord(Contract):
    """Reviewed historical incident preserved as a learning asset."""

    incident_id: str
    run_id: str | None = None
    source_run_id: str | None = None
    task_summary: str | None = None
    observed_pattern: str | None = None
    expected_behavior: str | None = None
    observed_behavior: str | None = None
    first_deviation_event_id: str | None = None
    failure_category: FailureCategory = (
        FailureCategory.UNKNOWN_INSUFFICIENT_EVIDENCE
    )
    label_status: LabelStatus = LabelStatus.SUSPECTED
    root_cause_status: str = "suspected"
    root_cause_summary: str | None = None
    root_cause_hypotheses: list[str] = Field(default_factory=list)
    verified_root_cause: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    affected_event_ids: list[str] = Field(default_factory=list)
    downstream_event_ids: list[str] = Field(default_factory=list)
    fix_ref: str | None = None
    verified_correction: str | None = None
    test_refs: list[str] = Field(default_factory=list)
    regression_test_refs: list[str] = Field(default_factory=list)
    replay_status: str = "not_run"
    data_origin: str = "controlled_fixture"
    provenance: str = "controlled_fixture"
    training_eligible: bool = False
    training_eligibility: str = "pending_review"
    review_status: str = "pending"
    dataset_version: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    reviewed_at: datetime | None = None


class IncidentMatch(Contract):
    """Similarity match result retrieved from historical incident store."""

    incident_id: str
    match_id: str | None = None
    run_id: str | None = None
    similarity_score: float = Field(ge=0, le=1)
    score_kind: str = "similarity_score"
    match_reason: str = ""
    why_relevant: str | None = None
    matched_features: list[str] = Field(default_factory=list)
    verified: bool = False
    retrieved_at: datetime = Field(default_factory=utc_now)


class PredictionResult(Contract):
    """Failure prediction produced by the trained baseline or rules pipeline."""

    run_id: str
    prediction_id: str | None = None
    model_version: str = "baseline-v1"
    dataset_version: str = "dataset-v1"
    prediction_mode: str = "trained_classifier"
    predicted_categories: list[str] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    score_meaning: str = "probability"
    abstained: bool = False
    abstention_reason: str | None = None
    supporting_incident_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Patch & Verification Records
# ---------------------------------------------------------------------------


class PatchRecord(Contract):
    """Candidate remediation patch created in an isolated sandbox worktree."""

    patch_id: str
    run_id: str
    hypothesis_id: str
    workspace_ref: str
    diff_ref: str | None = None
    diff_path: str | None = None
    status: str = "proposed"
    human_approved: bool = False
    requires_human_review: bool = True
    created_at: datetime = Field(default_factory=utc_now)


class VerificationReport(Contract):
    """Verification report combining test execution and replay validation."""

    report_id: str | None = None
    verification_id: str | None = None
    run_id: str | None = None
    patch_id: str | None = None
    passed: bool = False
    total: int = 0
    failures: int = 0
    command: str | None = None
    output_ref: str | None = None
    targeted_test_status: str = "not_run"
    regression_test_status: str = "not_run"
    replay_status: str = "not_run"
    baseline_run_id: str | None = None
    baseline_run_ref: str | None = None
    corrected_run_id: str | None = None
    replay_run_ref: str | None = None
    summary: str = ""
    tested_at: datetime = Field(default_factory=utc_now)


TestReport = VerificationReport  # Canonical alias
ReplayReport = VerificationReport  # Canonical alias
