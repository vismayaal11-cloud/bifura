"""Deterministic safety policy evaluation for Bifura tools.

Member 2 ownership. Implements evaluate_tool_action to evaluate proposed tool
actions against deterministic backend safety rules without invoking tools or LLMs.
"""

from collections.abc import Callable
from datetime import datetime
import ast
import math
from pathlib import Path
from typing import Any
import uuid

from bifura.schemas.models import (
    ExecutionStatus,
    SafetyDecisionRecord,
    SafetyDecisionType,
    ToolCallProposal,
    utc_now,
)

# Windows reserved device names that must be rejected regardless of extension
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

# Sensitive files/directories forbidden from read access
FORBIDDEN_TARGETS = {
    ".env",
    ".git",
    ".venv",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
}

# Calculator safety limits shared with local_tools
MAX_EXPR_LENGTH = 200
MAX_NUMERIC_LITERAL = 1e12
MAX_EXPONENT_MAGNITUDE = 100
MAX_RESULT_MAGNITUDE = 1e12


def _default_id_generator() -> str:
    return f"dec-{uuid.uuid4().hex[:12]}"


def _check_path_safety(raw_path: str) -> tuple[bool, str]:
    """Perform security and syntactic checks on a path string."""
    if not isinstance(raw_path, str):
        return False, "Path must be a string."
    if not raw_path.strip():
        return False, "Path cannot be empty or whitespace only."
    if "\0" in raw_path:
        return False, "Null bytes are forbidden in paths."
    if ":" in raw_path:
        return False, "Drive letters and alternate data streams are forbidden."
    if raw_path.startswith(("/", "\\", "//", "\\\\")):
        return False, "Absolute and UNC paths are forbidden."

    p = Path(raw_path)
    if p.is_absolute() or p.drive:
        return False, "Absolute and drive paths are forbidden."

    for part in p.parts:
        base = part.split(".")[0].upper()
        if base in RESERVED_NAMES:
            return False, f"Path component '{part}' is a reserved Windows device name."

    return True, ""


def _validate_and_evaluate_calculator(expression: str) -> tuple[bool, float | None, str]:
    """Validate arithmetic expression with restricted AST and compute bounded result."""
    if not isinstance(expression, str):
        return False, None, "Expression must be a string."
    if len(expression) > MAX_EXPR_LENGTH:
        return False, None, f"Expression exceeds maximum length of {MAX_EXPR_LENGTH} characters."
    if not expression.strip():
        return False, None, "Expression cannot be empty."

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        return False, None, f"Syntax error in expression: {e}"

    if not isinstance(tree, ast.Expression):
        return False, None, "Root AST node must be an Expression."

    # Validate AST node types
    for node in ast.walk(tree):
        if isinstance(node, ast.Expression):
            continue
        elif isinstance(
            node,
            (
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.Div,
                ast.FloorDiv,
                ast.Mod,
                ast.Pow,
                ast.UAdd,
                ast.USub,
            ),
        ):
            continue
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return False, None, "Boolean literals are rejected as numeric operands."
            if isinstance(node.value, complex):
                return False, None, "Complex numbers are prohibited."
            if not isinstance(node.value, (int, float)):
                return False, None, f"Unsupported constant type: {type(node.value).__name__}."
            if abs(node.value) > MAX_NUMERIC_LITERAL:
                return False, None, f"Numeric literal {node.value} exceeds maximum allowed of {MAX_NUMERIC_LITERAL}."
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, (ast.UAdd, ast.USub)):
                return False, None, f"Unsupported unary operator: {type(node.op).__name__}."
        elif isinstance(node, ast.BinOp):
            allowed_ops = (
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.Div,
                ast.FloorDiv,
                ast.Mod,
                ast.Pow,
            )
            if not isinstance(node.op, allowed_ops):
                return False, None, f"Unsupported binary operator: {type(node.op).__name__}."
            # Protect against nested exponentiation chains like 9 ** 9 ** 9
            if isinstance(node.op, ast.Pow):
                if isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.Pow):
                    return False, None, "Nested exponentiation chain rejected during AST check before computation."
                if isinstance(node.right, ast.BinOp) and isinstance(node.right.op, ast.Pow):
                    return False, None, "Nested exponentiation chain rejected during AST check before computation."
        else:
            return False, None, f"Prohibited AST node: {type(node).__name__}."

    def _eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand)
            val = -operand if isinstance(node.op, ast.USub) else +operand
            if abs(val) > MAX_RESULT_MAGNITUDE:
                raise ValueError("Intermediate result exceeds maximum allowed magnitude.")
            return val
        if isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow):
                left = _eval_node(node.left)
                right = _eval_node(node.right)
                if abs(right) > MAX_EXPONENT_MAGNITUDE:
                    raise ValueError(f"Exponent magnitude {right} exceeds {MAX_EXPONENT_MAGNITUDE}.")
                if left == 0 and right < 0:
                    raise ZeroDivisionError("Zero cannot be raised to a negative power.")
                try:
                    res = left ** right
                except OverflowError:
                    raise ValueError("Exponentiation resulted in overflow.")
            elif isinstance(node.op, ast.Div):
                left = _eval_node(node.left)
                right = _eval_node(node.right)
                if right == 0:
                    raise ZeroDivisionError("Division by zero.")
                res = left / right
            elif isinstance(node.op, ast.FloorDiv):
                left = _eval_node(node.left)
                right = _eval_node(node.right)
                if right == 0:
                    raise ZeroDivisionError("Floor division by zero.")
                res = left // right
            elif isinstance(node.op, ast.Mod):
                left = _eval_node(node.left)
                right = _eval_node(node.right)
                if right == 0:
                    raise ZeroDivisionError("Modulo by zero.")
                res = left % right
            elif isinstance(node.op, ast.Add):
                res = _eval_node(node.left) + _eval_node(node.right)
            elif isinstance(node.op, ast.Sub):
                res = _eval_node(node.left) - _eval_node(node.right)
            elif isinstance(node.op, ast.Mult):
                res = _eval_node(node.left) * _eval_node(node.right)
            else:
                raise ValueError(f"Unsupported binary operator: {type(node.op).__name__}.")

            if math.isnan(res) or math.isinf(res):
                raise ValueError("Calculation produced non-finite result.")
            if isinstance(res, complex):
                raise ValueError("Complex numbers are prohibited.")
            if abs(res) > MAX_RESULT_MAGNITUDE:
                raise ValueError(f"Result {res} exceeds maximum allowed magnitude of {MAX_RESULT_MAGNITUDE}.")
            return float(res)

        raise ValueError(f"Unexpected AST node: {type(node).__name__}.")

    try:
        result = _eval_node(tree)
        return True, result, ""
    except (ZeroDivisionError, ValueError, OverflowError) as e:
        return False, None, str(e)


def evaluate_tool_action(
    proposal: ToolCallProposal,
    context: dict[str, Any],
    clock: Callable[[], datetime] | None = None,
    id_generator: Callable[[], str] | None = None,
) -> SafetyDecisionRecord:
    """Evaluate a proposed tool action against deterministic safety policies.

    Must return a valid SafetyDecisionRecord (ALLOW, REVIEW, or BLOCK).
    Does NOT invoke any tool implementation.
    Records the pre-execution status (e.g. BLOCKED_BEFORE_EXECUTION or NOT_STARTED).
    """
    now = clock() if clock is not None else utc_now()
    if id_generator is not None:
        raw_id = id_generator()
        decision_id = raw_id if raw_id.startswith("dec-") else f"dec-{raw_id}"
    else:
        decision_id = _default_id_generator()

    # 1. Validate Context Keys
    required_context_keys = [
        "workspace_root",
        "sandbox_root",
        "allowed_tools",
        "permissions",
        "provenance",
        "mode",
    ]
    missing_keys = [k for k in required_context_keys if k not in context]
    if missing_keys:
        return SafetyDecisionRecord(
            decision_id=decision_id,
            decision=SafetyDecisionType.BLOCK,
            proposal_id=proposal.proposal_id,
            tool_call_id=proposal.tool_call_id,
            run_id=proposal.run_id,
            policy_rule="invalid_context",
            rule_ids=["invalid_context"],
            reason=f"Context is missing required keys: {', '.join(missing_keys)}.",
            execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
            review_status="not_required",
            decided_at=now,
            created_at=now,
        )

    allowed_tools = context.get("allowed_tools", [])
    permissions = context.get("permissions", {})

    # 2. Check Allowed Tools
    if proposal.tool_name not in allowed_tools:
        return SafetyDecisionRecord(
            decision_id=decision_id,
            decision=SafetyDecisionType.BLOCK,
            proposal_id=proposal.proposal_id,
            tool_call_id=proposal.tool_call_id,
            run_id=proposal.run_id,
            policy_rule="unauthorized_tool",
            rule_ids=["unauthorized_tool"],
            reason=f"Tool '{proposal.tool_name}' is not in allowed_tools list.",
            execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
            review_status="not_required",
            decided_at=now,
            created_at=now,
        )

    # 3. Check Explicit Human Review Requirements
    requires_review = (
        context.get("require_review", False)
        or proposal.arguments.get("requires_review", False)
        or proposal.model_generated_metadata.get("requires_review", False)
        or proposal.tool_name in context.get("review_tools", [])
        or proposal.tool_name in {"human_review", "ask_human"}
    )
    if requires_review:
        return SafetyDecisionRecord(
            decision_id=decision_id,
            decision=SafetyDecisionType.REVIEW,
            proposal_id=proposal.proposal_id,
            tool_call_id=proposal.tool_call_id,
            run_id=proposal.run_id,
            policy_rule="human_authorization_required",
            rule_ids=["human_authorization_required"],
            reason=f"Action '{proposal.tool_name}' requires authorized human review before execution.",
            execution_status=ExecutionStatus.AWAITING_REVIEW,
            review_status="pending",
            decided_at=now,
            created_at=now,
        )

    # 4. Tool-Specific Policy Evaluators
    if proposal.tool_name == "read_file":
        raw_path = proposal.arguments.get("path")
        if not isinstance(raw_path, str):
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="invalid_arguments",
                rule_ids=["invalid_arguments"],
                reason="Argument 'path' must be provided as a string.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        is_safe, error_msg = _check_path_safety(raw_path)
        if not is_safe:
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="workspace_containment",
                rule_ids=["workspace_containment"],
                reason=f"Target path rejected: {error_msg}",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        # Check containment inside workspace_root
        workspace = Path(context["workspace_root"]).resolve()
        target = (workspace / raw_path).resolve(strict=False)

        try:
            target.relative_to(workspace)
            escapes_workspace = False
        except ValueError:
            escapes_workspace = True

        if escapes_workspace or target == workspace:
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="workspace_containment",
                rule_ids=["workspace_containment"],
                reason=f"Target path {raw_path} escapes authorized workspace root.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        # Check for forbidden sensitive targets (.env, .git, .venv, ssh keys)
        if any(part in FORBIDDEN_TARGETS or part.startswith(".env") for part in target.parts):
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="protected_resource",
                rule_ids=["protected_resource"],
                reason=f"Target path '{raw_path}' accesses protected files or directories.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        return SafetyDecisionRecord(
            decision_id=decision_id,
            decision=SafetyDecisionType.ALLOW,
            proposal_id=proposal.proposal_id,
            tool_call_id=proposal.tool_call_id,
            run_id=proposal.run_id,
            policy_rule="workspace_containment",
            rule_ids=["workspace_containment"],
            reason=f"Path '{raw_path}' is strictly contained within authorized workspace root.",
            validated_target=str(target),
            execution_status=ExecutionStatus.NOT_STARTED,
            review_status="not_required",
            decided_at=now,
            created_at=now,
        )

    elif proposal.tool_name == "write_file":
        raw_path = proposal.arguments.get("path")
        content = proposal.arguments.get("content")

        if not isinstance(raw_path, str) or not isinstance(content, str):
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="invalid_arguments",
                rule_ids=["invalid_arguments"],
                reason="Arguments 'path' and 'content' must be strings.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        # Check explicit permissions: write_sandbox must be True
        if permissions.get("write_sandbox") is not True:
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="sandbox_write_permission",
                rule_ids=["sandbox_write_permission"],
                reason="Permission 'write_sandbox' is not granted.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        # write_project is ALWAYS False
        if permissions.get("write_project") is True:
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="sandbox_containment",
                rule_ids=["sandbox_containment"],
                reason="Permission 'write_project' is forbidden.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        is_safe, error_msg = _check_path_safety(raw_path)
        if not is_safe:
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="sandbox_containment",
                rule_ids=["sandbox_containment"],
                reason=f"Target path rejected: {error_msg}",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        # Path must resolve strictly inside sandbox_root
        sandbox = Path(context["sandbox_root"]).resolve()
        target = (sandbox / raw_path).resolve(strict=False)

        try:
            target.relative_to(sandbox)
            escapes_sandbox = False
        except ValueError:
            escapes_sandbox = True

        if escapes_sandbox or target == sandbox:
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="sandbox_containment",
                rule_ids=["sandbox_containment"],
                reason=f"Target path '{raw_path}' escapes authorized sandbox root.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        # Check for forbidden sensitive targets
        if any(part in FORBIDDEN_TARGETS or part.startswith(".env") for part in target.parts):
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="protected_resource",
                rule_ids=["protected_resource"],
                reason=f"Target path '{raw_path}' accesses protected files or directories.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        return SafetyDecisionRecord(
            decision_id=decision_id,
            decision=SafetyDecisionType.ALLOW,
            proposal_id=proposal.proposal_id,
            tool_call_id=proposal.tool_call_id,
            run_id=proposal.run_id,
            policy_rule="sandbox_containment",
            rule_ids=["sandbox_containment"],
            reason=f"Write target '{raw_path}' is strictly contained within authorized sandbox root and write_sandbox permission is granted.",
            validated_target=str(target),
            execution_status=ExecutionStatus.NOT_STARTED,
            review_status="not_required",
            decided_at=now,
            created_at=now,
        )

    elif proposal.tool_name == "calculate":
        expression = proposal.arguments.get("expression")
        if not isinstance(expression, str):
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="invalid_arguments",
                rule_ids=["invalid_arguments"],
                reason="Argument 'expression' must be provided as a string.",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        is_valid, result, error_msg = _validate_and_evaluate_calculator(expression)
        if not is_valid:
            return SafetyDecisionRecord(
                decision_id=decision_id,
                decision=SafetyDecisionType.BLOCK,
                proposal_id=proposal.proposal_id,
                tool_call_id=proposal.tool_call_id,
                run_id=proposal.run_id,
                policy_rule="safe_calculator",
                rule_ids=["safe_calculator"],
                reason=f"Calculator safety check failed: {error_msg}",
                execution_status=ExecutionStatus.BLOCKED_BEFORE_EXECUTION,
                review_status="not_required",
                decided_at=now,
                created_at=now,
            )

        return SafetyDecisionRecord(
            decision_id=decision_id,
            decision=SafetyDecisionType.ALLOW,
            proposal_id=proposal.proposal_id,
            tool_call_id=proposal.tool_call_id,
            run_id=proposal.run_id,
            policy_rule="safe_calculator",
            rule_ids=["safe_calculator"],
            reason=f"Expression '{expression}' is valid arithmetic within safety bounds (result: {result}).",
            execution_status=ExecutionStatus.NOT_STARTED,
            review_status="not_required",
            decided_at=now,
            created_at=now,
        )

    # Any other unrecognized allowed tool defaults to REVIEW
    return SafetyDecisionRecord(
        decision_id=decision_id,
        decision=SafetyDecisionType.REVIEW,
        proposal_id=proposal.proposal_id,
        tool_call_id=proposal.tool_call_id,
        run_id=proposal.run_id,
        policy_rule="unrecognized_tool_review",
        rule_ids=["unrecognized_tool_review"],
        reason=f"Tool '{proposal.tool_name}' requires human authorization.",
        execution_status=ExecutionStatus.AWAITING_REVIEW,
        review_status="pending",
        decided_at=now,
        created_at=now,
    )
