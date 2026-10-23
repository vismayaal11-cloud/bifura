"""Run bundle validation schema for Bifura execution, safety, and learning artifacts."""

from pydantic import Field

from bifura.schemas.models import (
    Contract,
    DeviationRecord,
    ImpactGraph,
    IncidentMatch,
    IncidentRecord,
    PredictionResult,
    RunRecord,
    SafetyDecisionRecord,
    ToolExecutionResult,
    TraceEvent,
    VerificationReport,
)


class RunBundle(Contract):
    """Canonical run bundle validating execution, safety, and learning artifacts.

    Member 1 produces the initial bundle (with incident matches, incident records,
    and prediction set to null). Member 3 supplies genuine incident matches,
    records, and prediction during integration.
    """

    schema_version: str = "1.0"
    scenario_id: str
    run: RunRecord
    expected_action_sequence: list[str] = Field(default_factory=list)
    actual_execution_summary: str = ""
    events: list[TraceEvent] = Field(default_factory=list)
    safety_decisions: list[SafetyDecisionRecord] = Field(default_factory=list)
    execution_results: list[ToolExecutionResult] = Field(default_factory=list)
    deviation: DeviationRecord | None = None
    incident_matches: list[IncidentMatch] | None = None
    incident_records: list[IncidentRecord] | None = None
    prediction: PredictionResult | None = None
    impact_graph: ImpactGraph | None = None
    verification: VerificationReport | None = None
