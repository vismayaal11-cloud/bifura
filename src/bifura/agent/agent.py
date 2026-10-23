"""Deterministic LangGraph agent workflow for Bifura demo scenarios.

Implements multi-step task execution using local tools through the central executor,
with explicit support for four standardized demo scenarios:
- success
- wrong_path
- stale_state
- wrong_sequence

Uses a transparent deterministic planner (no LLM, no API key required).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from bifura.schemas.models import (
    ExecutionStatus,
    SafetyDecisionRecord,
    SafetyDecisionType,
    ToolCallProposal,
    ToolExecutionResult,
    TraceEvent,
    utc_now,
)
from bifura.tools.executor import execute_tool_action
from bifura.tools.local_tools import (
    MAX_EXPRESSION_LENGTH,
    MAX_NUMERIC_LITERAL,
    calculate,
    read_file,
    write_file,
)
from bifura.tracing.recorder import TraceRecorder


def default_policy_evaluator(
    proposal: ToolCallProposal,
    context: dict[str, Any],
) -> SafetyDecisionRecord:
    """Default deterministic safety policy evaluator conforming to contract rules."""
    allowed_tools = context.get("allowed_tools", ["read_file", "calculate", "write_file"])
    dec_id = f"dec-{proposal.proposal_id}"
    now_fn = context.get("_clock", utc_now)
    now = now_fn()
    if proposal.tool_name not in allowed_tools:
        return SafetyDecisionRecord(
            decision_id=dec_id,
            decision=SafetyDecisionType.BLOCK,
            proposal_id=proposal.proposal_id,
            run_id=proposal.run_id,
            policy_rule="tool_allowlist_guard",
            reason=f"Tool '{proposal.tool_name}' is not in allowed_tools list.",
            execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
            decided_at=now,
            created_at=now,
        )

    # 1. read_file checks
    if proposal.tool_name == "read_file":
        path_arg = proposal.arguments.get("path", "")
        if not path_arg or not isinstance(path_arg, str):
            return SafetyDecisionRecord(
                decision_id=dec_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="argument_validation",
                reason="Path argument must be a non-empty string.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                decided_at=now,
                created_at=now,
            )

        # Check for path traversal or escaping workspace_root
        workspace_root = context.get("workspace_root")
        if not workspace_root:
            return SafetyDecisionRecord(
                decision_id=dec_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="workspace_root_guard",
                reason="Missing workspace_root in context.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                decided_at=now,
                created_at=now,
            )

        resolved_root = Path(workspace_root).resolve()
        target = Path(workspace_root, path_arg).resolve()
        try:
            target.relative_to(resolved_root)
        except ValueError:
            return SafetyDecisionRecord(
                decision_id=dec_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="path_containment_policy",
                reason=f"Relative path traversal escaping workspace root: '{path_arg}'.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                decided_at=now,
                created_at=now,
            )

        if ".." in Path(path_arg).parts:
            return SafetyDecisionRecord(
                decision_id=dec_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="path_traversal_policy",
                reason="Path traversal component ('..') detected.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                decided_at=now,
                created_at=now,
            )

        return SafetyDecisionRecord(
            decision_id=dec_id,
            decision=SafetyDecisionType.ALLOW,
            proposal_id=proposal.proposal_id,
            run_id=proposal.run_id,
            policy_rule="read_file_allow",
            reason="Read target resolves safely within workspace_root.",
            execution_status=ExecutionStatus.NOT_STARTED,
            decided_at=now,
            created_at=now,
        )

    # 2. write_file checks
    if proposal.tool_name == "write_file":
        permissions = context.get("permissions", {})
        if not permissions.get("write_sandbox", False):
            return SafetyDecisionRecord(
                decision_id=dec_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="sandbox_permission_guard",
                reason="Write operation prohibited: permissions['write_sandbox'] is False.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                decided_at=now,
                created_at=now,
            )

        sandbox_root = context.get("sandbox_root")
        if not sandbox_root:
            return SafetyDecisionRecord(
                decision_id=dec_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="sandbox_root_guard",
                reason="Missing sandbox_root in context.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                decided_at=now,
                created_at=now,
            )

        path_arg = proposal.arguments.get("path", "")
        resolved_sandbox = Path(sandbox_root).resolve()
        target = Path(sandbox_root, path_arg).resolve()
        try:
            target.relative_to(resolved_sandbox)
        except ValueError:
            return SafetyDecisionRecord(
                decision_id=dec_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="sandbox_containment_policy",
                reason=f"Write target escapes sandbox_root: '{path_arg}'.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                decided_at=now,
                created_at=now,
            )

        return SafetyDecisionRecord(
            decision_id=dec_id,
            decision=SafetyDecisionType.ALLOW,
            proposal_id=proposal.proposal_id,
            run_id=proposal.run_id,
            policy_rule="write_file_allow",
            reason="Write target resolves safely inside sandbox_root with write_sandbox=True.",
            execution_status=ExecutionStatus.NOT_STARTED,
            decided_at=now,
            created_at=now,
        )

    # 3. calculate checks
    if proposal.tool_name == "calculate":
        expr = proposal.arguments.get("expression", "")
        if not isinstance(expr, str) or not expr.strip() or len(expr) > MAX_EXPRESSION_LENGTH:
            return SafetyDecisionRecord(
                decision_id=dec_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                policy_rule="calculator_limits",
                reason="Expression is invalid or exceeds character limit.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                decided_at=now,
                created_at=now,
            )

        return SafetyDecisionRecord(
            decision_id=dec_id,
            decision=SafetyDecisionType.ALLOW,
            proposal_id=proposal.proposal_id,
            run_id=proposal.run_id,
            policy_rule="calculate_allow",
            reason="Arithmetic expression within policy limits.",
            execution_status=ExecutionStatus.NOT_STARTED,
            decided_at=now,
            created_at=now,
        )

    return SafetyDecisionRecord(
        decision_id=dec_id,
        decision=SafetyDecisionType.BLOCK,
        proposal_id=proposal.proposal_id,
        run_id=proposal.run_id,
        policy_rule="default_deny",
        reason=f"No policy rule allows tool '{proposal.tool_name}'.",
        execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
        decided_at=now,
        created_at=now,
    )


class AgentState(TypedDict):
    """Execution state tracked across the LangGraph workflow."""

    run_id: str
    scenario_id: str
    task_text: str
    context: dict[str, Any]
    current_step: int
    read_content: str | None
    calculated_result: float | None
    written_path: str | None
    status: str
    completed: bool
    blocked: bool
    error: str | None
    planned_actions: list[dict[str, Any]]
    execution_summary: str


@dataclass
class AgentRunResult:
    """Structured result returned from executing the LangGraph agent."""

    run_id: str
    scenario_id: str
    status: str
    events: list[TraceEvent]
    safety_decisions: list[SafetyDecisionRecord]
    execution_results: list[ToolExecutionResult]
    actual_execution_summary: str
    final_state: dict[str, Any]


class BifuraAgent:
    """Deterministic LangGraph agent for Bifura multi-step tool execution."""

    def __init__(
        self,
        evaluator: Callable[[ToolCallProposal, dict[str, Any]], SafetyDecisionRecord] | None = None,
        clock: Callable[[], datetime] = utc_now,
        id_generator: Callable[[], str] | None = None,
    ) -> None:
        self.evaluator = evaluator or default_policy_evaluator
        self.clock = clock
        self.id_generator = id_generator

    def _plan_actions(self, scenario_id: str) -> list[dict[str, Any]]:
        """Deterministic planner generating action steps per scenario."""
        if scenario_id == "success":
            return [
                {"tool": "read_file", "args": {"path": "fixtures/scenario_1.txt"}},
                {"tool": "calculate", "args": {"expression": "{from_read}"}},
                {"tool": "write_file", "args": {"path": "result.txt", "content": "{from_calc}"}},
            ]
        if scenario_id == "wrong_path":
            return [
                {"tool": "read_file", "args": {"path": "../../secrets.txt"}},
                {"tool": "calculate", "args": {"expression": "{from_read}"}},
                {"tool": "write_file", "args": {"path": "result.txt", "content": "{from_calc}"}},
            ]
        if scenario_id == "stale_state":
            # Controlled fault injection: references stale cached "2 + 3" instead of fresh "15 * 4"
            return [
                {"tool": "read_file", "args": {"path": "fixtures/scenario_1.txt"}},
                {"tool": "calculate", "args": {"expression": "2 + 3"}, "stale": True},
                {"tool": "write_file", "args": {"path": "result.txt", "content": "{from_calc}"}},
            ]
        if scenario_id == "wrong_sequence":
            # Controlled fault injection: premature write attempted before calculate
            return [
                {"tool": "read_file", "args": {"path": "fixtures/scenario_1.txt"}},
                {"tool": "write_file", "args": {"path": "result.txt", "content": "uncomputed"}},
                {"tool": "calculate", "args": {"expression": "{from_read}"}},
            ]

        # Generic default sequence
        return [
            {"tool": "read_file", "args": {"path": "fixtures/scenario_1.txt"}},
            {"tool": "calculate", "args": {"expression": "{from_read}"}},
            {"tool": "write_file", "args": {"path": "result.txt", "content": "{from_calc}"}},
        ]

    def run(
        self,
        task_text: str,
        scenario_id: str,
        context: dict[str, Any],
        run_id: str | None = None,
    ) -> AgentRunResult:
        """Run the LangGraph workflow synchronously and return the AgentRunResult."""
        actual_run_id = run_id or f"run-{scenario_id}-{uuid.uuid4().hex[:6]}"
        recorder = TraceRecorder(
            run_id=actual_run_id,
            clock=self.clock,
            id_generator=self.id_generator,
        )

        decisions_list: list[SafetyDecisionRecord] = []
        results_list: list[ToolExecutionResult] = []

        # Graph node functions
        def plan_node(state: AgentState) -> dict[str, Any]:
            recorder.record_task_started(state["task_text"], state["scenario_id"])
            actions = self._plan_actions(state["scenario_id"])
            return {"planned_actions": actions, "current_step": 0}

        def execute_step_node(state: AgentState) -> dict[str, Any]:
            step_idx = state["current_step"]
            action = state["planned_actions"][step_idx]
            tool_name = action["tool"]
            raw_args = dict(action["args"])

            # Resolve dynamic arguments
            if tool_name == "calculate" and raw_args.get("expression") == "{from_read}":
                raw_args["expression"] = state["read_content"] or ""
            elif tool_name == "write_file" and raw_args.get("content") == "{from_calc}":
                raw_args["content"] = str(state["calculated_result"])

            # Invariant checks for controlled fault scenarios
            if state["scenario_id"] == "stale_state" and action.get("stale"):
                # Discrepancy between expected read expression and stale cached expression
                recorder.record_assertion_failed(
                    description="Discrepancy detected: calculation expression ('2 + 3') does not match freshly read content ('15 * 4')",
                    expected="15 * 4",
                    actual="2 + 3",
                )

            if state["scenario_id"] == "wrong_sequence" and tool_name == "write_file" and state.get("calculated_result") is None:
                recorder.record_assertion_failed(
                    description="Workflow precondition violated: attempted write_file before calculation completed",
                    expected="calculate_before_write",
                    actual="write_before_calculate",
                )

            # Build proposal
            prop_id = f"prop-{step_idx + 1:03d}"
            proposal = ToolCallProposal(
                proposal_id=prop_id,
                tool_name=tool_name,
                run_id=state["run_id"],
                arguments=raw_args,
            )

            # Record proposal
            deps = []
            if tool_name == "calculate" and state.get("read_content"):
                data_deps = ["file_content"]
            elif tool_name == "write_file" and state.get("calculated_result") is not None:
                data_deps = ["calculated_result"]
            else:
                data_deps = []

            recorder.record_tool_proposed(
                proposal=proposal,
                data_deps=data_deps,
            )

            # Execute through central executor
            decision, exec_result = execute_tool_action(
                proposal=proposal,
                context=state["context"],
                evaluator=self.evaluator,
                clock=self.clock,
                id_generator=self.id_generator or (lambda: uuid.uuid4().hex[:8]),
            )

            decisions_list.append(decision)
            results_list.append(exec_result)

            recorder.record_safety_decision(decision, proposal)

            updates: dict[str, Any] = {"current_step": step_idx + 1}

            if decision.decision == SafetyDecisionType.BLOCK:
                recorder.record_tool_blocked(decision, proposal)
                updates["blocked"] = True
                updates["status"] = "blocked"
                return updates

            if decision.decision == SafetyDecisionType.REVIEW:
                updates["blocked"] = True
                updates["status"] = "needs_review"
                return updates

            # Execution was allowed
            if exec_result.success:
                recorder.record_tool_started(proposal)
                recorder.record_tool_completed(proposal, exec_result, data_deps=data_deps)

                delta: dict[str, Any] = {}
                if tool_name == "read_file" and exec_result.result_data:
                    updates["read_content"] = exec_result.result_data.get("content")
                    delta["read_content"] = updates["read_content"]
                elif tool_name == "calculate" and exec_result.result_data:
                    updates["calculated_result"] = exec_result.result_data.get("result")
                    delta["calculated_result"] = updates["calculated_result"]
                elif tool_name == "write_file" and exec_result.result_data:
                    updates["written_path"] = exec_result.result_data.get("path")
                    delta["written_path"] = updates["written_path"]

                recorder.record_state_updated(delta)
            else:
                recorder.record_tool_started(proposal)
                recorder.record_error(proposal, exec_result)
                updates["error"] = exec_result.error_message
                updates["status"] = "failed"

            return updates

        def should_continue(state: AgentState) -> str:
            if state["blocked"] or state["error"]:
                return "finish_node"
            if state["current_step"] >= len(state["planned_actions"]):
                return "finish_node"
            return "execute_step_node"

        def finish_node(state: AgentState) -> dict[str, Any]:
            # Final status calculation
            if state["blocked"]:
                final_status = "blocked"
                summary = (
                    f"Run blocked by safety policy during {state['scenario_id']} scenario."
                )
            elif state["error"]:
                final_status = "failed"
                summary = f"Run failed with tool error: {state['error']}"
            elif state["scenario_id"] in ("stale_state", "wrong_sequence"):
                final_status = "failed"
                summary = (
                    f"Controlled fault injection; deterministic planner, no LLM. "
                    f"Scenario '{state['scenario_id']}' exhibited invariant failure."
                )
            else:
                final_status = "succeeded"
                summary = (
                    f"Task executed successfully inside sandbox. "
                    f"Result: {state.get('calculated_result')} written to {state.get('written_path')}."
                )

            recorder.record_run_finished(status=final_status, summary=summary)
            return {
                "status": final_status,
                "completed": True,
                "execution_summary": summary,
            }

        # Build workflow graph
        workflow = StateGraph(AgentState)
        workflow.add_node("plan_node", plan_node)
        workflow.add_node("execute_step_node", execute_step_node)
        workflow.add_node("finish_node", finish_node)

        workflow.add_edge(START, "plan_node")
        workflow.add_edge("plan_node", "execute_step_node")
        workflow.add_conditional_edges(
            "execute_step_node",
            should_continue,
            {
                "execute_step_node": "execute_step_node",
                "finish_node": "finish_node",
            },
        )
        workflow.add_edge("finish_node", END)

        app = workflow.compile()

        initial_state: AgentState = {
            "run_id": actual_run_id,
            "scenario_id": scenario_id,
            "task_text": task_text,
            "context": context,
            "current_step": 0,
            "read_content": None,
            "calculated_result": None,
            "written_path": None,
            "status": "pending",
            "completed": False,
            "blocked": False,
            "error": None,
            "planned_actions": [],
            "execution_summary": "",
        }

        final_state = app.invoke(initial_state)

        return AgentRunResult(
            run_id=actual_run_id,
            scenario_id=scenario_id,
            status=final_state["status"],
            events=recorder.get_events(),
            safety_decisions=decisions_list,
            execution_results=results_list,
            actual_execution_summary=final_state["execution_summary"],
            final_state=dict(final_state),
        )
