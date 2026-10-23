"""Impact graph construction from explicit trace event dependencies."""

from __future__ import annotations

from typing import Any

from bifura.schemas.models import DependencyEdge, EvidenceStatus, ImpactGraph, TraceEvent


def build_impact_graph(
    run_id: str,
    events: list[TraceEvent],
) -> ImpactGraph | None:
    """Build an ImpactGraph from explicit event dependencies and data references.

    Never invents causal edges. If no dependency evidence exists, returns None.

    Args:
        run_id: Unique run ID.
        events: List of recorded TraceEvents.

    Returns:
        ImpactGraph if dependencies exist, else None.
    """
    edges: list[DependencyEdge] = []
    nodes: list[dict[str, Any]] = []
    evidence_refs: list[str] = []

    for ev in events:
        nodes.append({
            "event_id": ev.event_id,
            "event_type": ev.event_type,
            "actor": ev.actor,
            "tool_name": ev.tool_name,
            "summary": ev.summary,
            "sequence": ev.sequence,
        })

        if ev.depends_on_event_ids:
            for dep_id in ev.depends_on_event_ids:
                edge = DependencyEdge(
                    edge_id=f"edge-{dep_id}-{ev.event_id}",
                    from_event_id=dep_id,
                    to_event_id=ev.event_id,
                    run_id=run_id,
                    dependency_type="consumes_output",
                    evidence_status=EvidenceStatus.OBSERVED,
                    evidence_refs=[ev.event_id],
                    explanation=f"Event {ev.event_id} depends on output of {dep_id}",
                )
                edges.append(edge)
                evidence_refs.append(ev.event_id)

    if not edges:
        return None

    return ImpactGraph(
        run_id=run_id,
        nodes=nodes,
        edges=edges,
        evidence_refs=evidence_refs,
    )
