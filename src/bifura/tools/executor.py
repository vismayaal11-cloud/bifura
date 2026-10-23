"""Central tool executor for Bifura.

Enforces safety policy decisions and dispatches execution only to registered local tools
when authorized with SafetyDecisionType.ALLOW. Implements comprehensive fail-closed semantics.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from bifura.schemas.models import (
    ExecutionStatus,
    SafetyDecisionRecord,
    SafetyDecisionType,
    ToolCallProposal,
    ToolExecutionResult,
    utc_now,
)
from bifura.tools.local_tools import LOCAL_TOOL_REGISTRY, dispatch_local_tool


def execute_tool_action(
    proposal: ToolCallProposal,
    context: dict[str, Any],
    evaluator: Callable[[ToolCallProposal, dict[str, Any]], SafetyDecisionRecord] | None = None,
    clock: Callable[[], datetime] = utc_now,
    id_generator: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> tuple[SafetyDecisionRecord, ToolExecutionResult]:
    """Execute a proposed tool action only if the evaluator returns ALLOW.

    Enforces fail-closed safety semantics. Returns a tuple of:
    (SafetyDecisionRecord, ToolExecutionResult)
    using canonical Pydantic models.

    Args:
        proposal: Untrusted tool call proposal to evaluate and execute.
        context: Standard execution context dictionary.
        evaluator: Injected policy evaluator callable.
        clock: Injected clock for deterministic timestamps.
        id_generator: Injected generator for deterministic unique IDs.

    Returns:
        tuple containing the immutable (or fail-closed) SafetyDecisionRecord
        and the corresponding ToolExecutionResult.
    """
    now = clock()

    # Helper to generate fail-closed decision and execution result
    def _create_fail_closed(
        rule: str,
        reason: str,
        error_type: str = "SafetyBlockError",
        error_message: str = "Execution blocked by safety policy or evaluator failure.",
    ) -> tuple[SafetyDecisionRecord, ToolExecutionResult]:
        dec_id = f"dec-failclosed-{id_generator()}"
        decision = SafetyDecisionRecord(
            decision_id=dec_id,
            decision=SafetyDecisionType.BLOCK,
            proposal_id=proposal.proposal_id,
            tool_call_id=proposal.tool_call_id,
            run_id=proposal.run_id,
            policy_rule=rule,
            rule_ids=[rule],
            reason=reason,
            policy_version="1.0",
            execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
            review_status="not_required",
            decided_at=now,
            created_at=now,
        )
        result = ToolExecutionResult(
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            executed=False,
            success=False,
            result_data=None,
            error_type=error_type,
            error_message=error_message,
        )
        return decision, result

    # 1. Missing evaluator -> fail closed
    if evaluator is None:
        return _create_fail_closed(
            rule="fail_closed_guard",
            reason="Evaluator missing, threw exception, or returned invalid decision.",
        )

    # 2. Call evaluator with exception protection
    try:
        decision = evaluator(proposal, context)
    except Exception as exc:
        return _create_fail_closed(
            rule="fail_closed_guard",
            reason=f"Evaluator threw exception: {exc}",
        )

    # 3. Invalid evaluator return type -> fail closed
    if not isinstance(decision, SafetyDecisionRecord):
        return _create_fail_closed(
            rule="fail_closed_guard",
            reason="Evaluator returned an invalid decision object (not a SafetyDecisionRecord).",
        )

    # 4. Inconsistent proposal ID -> fail closed
    if decision.proposal_id is not None and decision.proposal_id != proposal.proposal_id:
        return _create_fail_closed(
            rule="fail_closed_guard",
            reason=(
                f"Evaluator decision proposal_id '{decision.proposal_id}' "
                f"does not match proposed action proposal_id '{proposal.proposal_id}'."
            ),
        )

    # 5. Review decision -> do not execute
    if decision.decision == SafetyDecisionType.REVIEW:
        result = ToolExecutionResult(
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            executed=False,
            success=None,
            result_data=None,
            error_type="AwaitingReviewError",
            error_message=f"Execution suspended pending human review: {decision.reason}",
        )
        return decision, result

    # 6. Block decision -> do not execute
    if decision.decision == SafetyDecisionType.BLOCK:
        result = ToolExecutionResult(
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            executed=False,
            success=False,
            result_data=None,
            error_type="SafetyBlockError",
            error_message=f"Execution blocked by safety policy: {decision.reason}",
        )
        return decision, result

    # 7. Decision is ALLOW, but tool is unregistered -> fail closed
    if proposal.tool_name not in LOCAL_TOOL_REGISTRY:
        return _create_fail_closed(
            rule="unregistered_tool_guard",
            reason=f"Tool '{proposal.tool_name}' is not in local tool registry.",
            error_type="UnregisteredToolError",
            error_message=f"Tool '{proposal.tool_name}' is unregistered and cannot be executed.",
        )

    # 8. Authorized execution: Invoke registered local tool
    try:
        output_data = dispatch_local_tool(
            tool_name=proposal.tool_name,
            arguments=proposal.arguments,
            context=context,
        )
        result = ToolExecutionResult(
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            executed=True,
            success=True,
            result_data=output_data,
            error_type=None,
            error_message=None,
        )
    except Exception as exc:
        # Tool was invoked but raised a runtime error
        result = ToolExecutionResult(
            proposal_id=proposal.proposal_id,
            decision_id=decision.decision_id,
            executed=True,
            success=False,
            result_data=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )

    return decision, result
