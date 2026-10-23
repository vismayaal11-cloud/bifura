"""Execution trace recorder for Bifura.

Records normalized trace events conforming strictly to canonical TraceEvent models,
agreed event vocabulary, canonical actors, and explicit causal dependencies.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from bifura.schemas.models import (
    ActorType,
    EventType,
    ExecutionStatus,
    SafetyDecisionRecord,
    SafetyDecisionType,
    ToolCallProposal,
    ToolExecutionResult,
    TraceEvent,
    utc_now,
)


class TraceRecorder:
    """Records chronological, schema-validated execution trace events for an agent run."""

    def __init__(
        self,
        run_id: str,
        clock: Callable[[], datetime] = utc_now,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        self.run_id = run_id
        self.clock = clock
        self.id_generator = id_generator
        self.events: list[TraceEvent] = []
        self._seq = 0
        self._last_completed_event_id: str | None = None

    def _next_event_id(self) -> str:
        if self.id_generator is not None:
            return self.id_generator()
        return f"ev-{self._seq:03d}"

    def record_event(
        self,
        event_type: str | EventType,
        actor: str | ActorType = ActorType.AGENT,
        name: str | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        parent_event_id: str | None = None,
        summary: str | None = None,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        state_delta: dict[str, Any] | None = None,
        status: str = "observed",
        error: str | None = None,
        error_type: str | None = None,
        depends_on_event_ids: list[str] | None = None,
        data_dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        agent_node: str | None = None,
    ) -> TraceEvent:
        """Create, record, and return a validated TraceEvent."""
        etype_str = event_type.value if isinstance(event_type, EventType) else str(event_type)
        actor_str = actor.value if isinstance(actor, ActorType) else str(actor)

        event = TraceEvent(
            run_id=self.run_id,
            event_id=self._next_event_id(),
            sequence=self._seq,
            event_type=etype_str,
            timestamp=self.clock(),
            parent_event_id=parent_event_id,
            actor=actor_str,
            name=name or etype_str,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            summary=summary,
            input_data=input_data,
            output_data=output_data,
            state_delta=state_delta,
            status=status,
            provenance="agent",
            error=error,
            error_type=error_type,
            depends_on_event_ids=depends_on_event_ids or [],
            data_dependencies=data_dependencies or [],
            metadata=metadata or {},
            agent_node=agent_node,
        )
        self.events.append(event)
        self._seq += 1
        return event

    def record_task_started(self, task_text: str, scenario_id: str) -> TraceEvent:
        """Record task start event."""
        return self.record_event(
            event_type=EventType.TASK_STARTED,
            actor=ActorType.AGENT,
            summary=f"Task started for scenario '{scenario_id}': {task_text}",
            input_data={"task_text": task_text, "scenario_id": scenario_id},
            agent_node="plan_node",
        )

    def record_tool_proposed(
        self,
        proposal: ToolCallProposal,
        parent_event_id: str | None = None,
        depends_on: list[str] | None = None,
        data_deps: list[str] | None = None,
    ) -> TraceEvent:
        """Record tool proposed by the agent."""
        return self.record_event(
            event_type=EventType.TOOL_PROPOSED,
            actor=ActorType.AGENT,
            tool_name=proposal.tool_name,
            tool_call_id=proposal.tool_call_id or proposal.proposal_id,
            parent_event_id=parent_event_id,
            summary=f"Proposed tool '{proposal.tool_name}' with args {proposal.arguments}",
            input_data=proposal.arguments,
            depends_on_event_ids=depends_on or ([] if self._last_completed_event_id is None else [self._last_completed_event_id]),
            data_dependencies=data_deps or [],
            agent_node="execute_step_node",
        )

    def record_safety_decision(
        self,
        decision: SafetyDecisionRecord,
        proposal: ToolCallProposal,
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        """Record safety decision from the policy evaluator."""
        summary = (
            f"Policy {decision.policy_rule} returned {decision.decision.value}: {decision.reason}"
        )
        return self.record_event(
            event_type=EventType.SAFETY_DECISION,
            actor=ActorType.SAFETY_ENGINE,
            tool_name=proposal.tool_name,
            tool_call_id=proposal.tool_call_id or proposal.proposal_id,
            parent_event_id=parent_event_id,
            summary=summary,
            output_data={
                "decision": decision.decision.value,
                "policy_rule": decision.policy_rule,
                "reason": decision.reason,
                "execution_status": decision.execution_status.value,
            },
            status="observed",
            agent_node="execute_step_node",
        )

    def record_tool_blocked(
        self,
        decision: SafetyDecisionRecord,
        proposal: ToolCallProposal,
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        """Record tool blocked by safety policy before execution."""
        return self.record_event(
            event_type=EventType.TOOL_BLOCKED,
            actor=ActorType.SAFETY_ENGINE,
            tool_name=proposal.tool_name,
            tool_call_id=proposal.tool_call_id or proposal.proposal_id,
            parent_event_id=parent_event_id,
            summary=f"Tool '{proposal.tool_name}' execution blocked: {decision.reason}",
            input_data=proposal.arguments,
            error=decision.reason,
            error_type="SafetyBlockError",
            status="blocked",
            agent_node="execute_step_node",
        )

    def record_tool_started(
        self,
        proposal: ToolCallProposal,
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        """Record tool invocation initiated after ALLOW decision."""
        return self.record_event(
            event_type=EventType.TOOL_STARTED,
            actor=ActorType.TOOL,
            tool_name=proposal.tool_name,
            tool_call_id=proposal.tool_call_id or proposal.proposal_id,
            parent_event_id=parent_event_id,
            summary=f"Tool '{proposal.tool_name}' execution initiated.",
            input_data=proposal.arguments,
            status="observed",
            agent_node="execute_step_node",
        )

    def record_tool_completed(
        self,
        proposal: ToolCallProposal,
        result: ToolExecutionResult,
        parent_event_id: str | None = None,
        data_deps: list[str] | None = None,
    ) -> TraceEvent:
        """Record successful tool execution completion."""
        event = self.record_event(
            event_type=EventType.TOOL_COMPLETED,
            actor=ActorType.TOOL,
            tool_name=proposal.tool_name,
            tool_call_id=proposal.tool_call_id or proposal.proposal_id,
            parent_event_id=parent_event_id,
            summary=f"Tool '{proposal.tool_name}' completed successfully.",
            input_data=proposal.arguments,
            output_data=result.result_data,
            status="success",
            data_dependencies=data_deps or [],
            agent_node="execute_step_node",
        )
        self._last_completed_event_id = event.event_id
        return event

    def record_error(
        self,
        proposal: ToolCallProposal,
        result: ToolExecutionResult,
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        """Record tool runtime failure."""
        return self.record_event(
            event_type=EventType.ERROR,
            actor=ActorType.TOOL,
            tool_name=proposal.tool_name,
            tool_call_id=proposal.tool_call_id or proposal.proposal_id,
            parent_event_id=parent_event_id,
            summary=f"Tool '{proposal.tool_name}' failed: {result.error_message}",
            input_data=proposal.arguments,
            error=result.error_message,
            error_type=result.error_type,
            status="failure",
            agent_node="execute_step_node",
        )

    def record_assertion_failed(
        self,
        description: str,
        expected: Any,
        actual: Any,
        parent_event_id: str | None = None,
        depends_on: list[str] | None = None,
    ) -> TraceEvent:
        """Record invariant or assertion failure."""
        return self.record_event(
            event_type=EventType.ASSERTION_FAILED,
            actor=ActorType.EVALUATOR,
            parent_event_id=parent_event_id,
            summary=description,
            input_data={"expected": str(expected), "actual": str(actual)},
            error=description,
            error_type="AssertionFailure",
            status="failure",
            depends_on_event_ids=depends_on or ([] if self._last_completed_event_id is None else [self._last_completed_event_id]),
            agent_node="execute_step_node",
        )

    def record_assertion_passed(
        self,
        description: str,
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        """Record passed assertion."""
        return self.record_event(
            event_type=EventType.ASSERTION_PASSED,
            actor=ActorType.EVALUATOR,
            parent_event_id=parent_event_id,
            summary=description,
            status="success",
            agent_node="execute_step_node",
        )

    def record_state_updated(
        self,
        state_delta: dict[str, Any],
        parent_event_id: str | None = None,
    ) -> TraceEvent:
        """Record agent state update."""
        return self.record_event(
            event_type=EventType.STATE_UPDATED,
            actor=ActorType.AGENT,
            parent_event_id=parent_event_id,
            summary=f"Agent state updated with {list(state_delta.keys())}",
            state_delta=state_delta,
            status="observed",
            agent_node="execute_step_node",
        )

    def record_run_finished(
        self,
        status: str,
        summary: str,
    ) -> TraceEvent:
        """Record end of agent run."""
        return self.record_event(
            event_type=EventType.RUN_FINISHED,
            actor=ActorType.AGENT,
            summary=summary,
            output_data={"status": status, "summary": summary},
            status=status,
            agent_node="finish_node",
        )

    def get_events(self) -> list[TraceEvent]:
        """Return the complete chronological list of recorded events."""
        return list(self.events)
