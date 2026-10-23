"""Local safe tool implementations for Bifura: read_file, write_file, calculate.

Enforces strict path containment, Windows reserved name checks, symlink defense,
and restricted AST calculator evaluation with standardized numeric limits.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import Any, Callable

# Calculator Limits defined in INTEGRATION_CONTRACT.md and calculator_cases.json
MAX_EXPRESSION_LENGTH = 200
MAX_NUMERIC_LITERAL = 1e12
MAX_EXPONENT_MAGNITUDE = 100
MAX_RESULT_MAGNITUDE = 1e12

# Windows reserved device names
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

FORBIDDEN_PATH_PARTS = {".env", ".git", ".venv", "id_rsa"}


class LocalToolError(Exception):
    """Base error for local tool execution."""


class SecurityViolationError(LocalToolError):
    """Raised when an operation violates path containment or security bounds."""


class CalculationError(LocalToolError):
    """Raised when expression calculation fails validation or evaluation."""


def _validate_path_component(part: str) -> None:
    """Validate a single path component for forbidden characters or reserved names."""
    if not part or part == ".":
        return
    if part == "..":
        raise SecurityViolationError("Path traversal ('..') is strictly prohibited.")
    if ":" in part:
        raise SecurityViolationError("Alternate data streams and drive specifiers (':') are prohibited.")
    # Check Windows reserved names
    stem = part.split(".")[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        raise SecurityViolationError(f"Target component '{part}' is a reserved Windows device name.")


def _sanitize_and_resolve_path(
    user_path: str,
    root_dir: str | Path,
    root_name: str = "root",
) -> Path:
    """Validate path string and verify containment component-by-component within root_dir."""
    if not isinstance(user_path, str) or not user_path.strip():
        raise SecurityViolationError("Path must be a non-empty string.")

    raw_path = user_path.strip()

    # Reject drive-letters, absolute paths, and UNC network paths
    if raw_path.startswith(("\\\\", "//")):
        raise SecurityViolationError("UNC network paths are prohibited.")
    if len(raw_path) >= 2 and raw_path[1] == ":":
        raise SecurityViolationError("Drive-letter paths are prohibited.")
    if raw_path.startswith(("/", "\\")):
        raise SecurityViolationError("Absolute root-leading paths are prohibited.")
    if ":" in raw_path:
        raise SecurityViolationError("Alternate data streams (':') are prohibited.")

    parsed_path = Path(raw_path)

    # Component by component check
    for part in parsed_path.parts:
        _validate_path_component(part)

    # Resolve root
    root_resolved = Path(root_dir).resolve()

    # Resolve target component by component to prevent symlink escape
    current = root_resolved
    for part in parsed_path.parts:
        current = (current / part).resolve()
        try:
            current.relative_to(root_resolved)
        except ValueError:
            raise SecurityViolationError(
                f"Path '{user_path}' resolves outside {root_name} ({root_resolved})."
            )

    # Check against sensitive files/folders
    for part in current.parts:
        if part in FORBIDDEN_PATH_PARTS:
            raise SecurityViolationError(
                f"Access to sensitive resource '{part}' is strictly forbidden."
            )

    # Final containment check
    try:
        current.relative_to(root_resolved)
    except ValueError:
        raise SecurityViolationError(
            f"Path '{user_path}' resolves outside {root_name} ({root_resolved})."
        )

    return current


def read_file(path: str, context: dict[str, Any]) -> dict[str, Any]:
    """Read a text file strictly contained within workspace_root.

    Args:
        path: Path relative to workspace_root.
        context: Execution context containing workspace_root.

    Returns:
        dict containing 'path', 'content', and 'bytes_read'.
    """
    workspace_root = context.get("workspace_root")
    if not workspace_root:
        raise SecurityViolationError("Missing 'workspace_root' in context.")

    target_path = _sanitize_and_resolve_path(
        user_path=path,
        root_dir=workspace_root,
        root_name="workspace_root",
    )

    # Recheck containment immediately before file access
    root_resolved = Path(workspace_root).resolve()
    try:
        target_path.resolve().relative_to(root_resolved)
    except ValueError:
        raise SecurityViolationError(
            f"Path '{path}' failed pre-read containment check."
        )

    if not target_path.exists():
        raise FileNotFoundError(f"File not found: '{path}' in workspace_root.")
    if not target_path.is_file():
        raise LocalToolError(f"Path is not a regular file: '{path}'.")

    content = target_path.read_text(encoding="utf-8")
    return {
        "path": path,
        "content": content,
        "bytes_read": len(content.encode("utf-8")),
    }


def write_file(path: str, content: str, context: dict[str, Any]) -> dict[str, Any]:
    """Write text content to a file strictly contained within sandbox_root.

    Requires context['permissions']['write_sandbox'] is True.

    Args:
        path: Path relative to sandbox_root.
        content: Text content to write.
        context: Execution context containing sandbox_root and permissions.

    Returns:
        dict containing 'path' and 'bytes_written'.
    """
    permissions = context.get("permissions", {})
    if not isinstance(permissions, dict) or not permissions.get("write_sandbox", False):
        raise SecurityViolationError(
            "Write failed: 'permissions[\"write_sandbox\"]' is False or missing."
        )

    sandbox_root = context.get("sandbox_root")
    if not sandbox_root:
        raise SecurityViolationError("Missing 'sandbox_root' in context.")

    # Ensure sandbox root directory exists
    sandbox_path = Path(sandbox_root).resolve()
    sandbox_path.mkdir(parents=True, exist_ok=True)

    target_path = _sanitize_and_resolve_path(
        user_path=path,
        root_dir=sandbox_path,
        root_name="sandbox_root",
    )

    # Recheck containment immediately before writing
    try:
        target_path.resolve().relative_to(sandbox_path)
    except ValueError:
        raise SecurityViolationError(
            f"Path '{path}' failed pre-write containment check."
        )

    if not isinstance(content, str):
        raise LocalToolError(f"'content' must be a string, got {type(content).__name__}.")

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")

    return {
        "path": path,
        "bytes_written": len(content.encode("utf-8")),
    }


def _check_nested_exponentiation(node: ast.AST) -> None:
    """Inspect AST for chained/nested exponentiation before evaluation."""
    for child in ast.walk(node):
        if isinstance(child, ast.BinOp) and isinstance(child.op, ast.Pow):
            if isinstance(child.left, ast.BinOp) and isinstance(child.left.op, ast.Pow):
                raise CalculationError("Nested exponentiation chain rejected during AST check.")
            if isinstance(child.right, ast.BinOp) and isinstance(child.right.op, ast.Pow):
                raise CalculationError("Nested exponentiation chain rejected during AST check.")


def _safe_eval_ast(node: ast.AST) -> float:
    """Recursively and safely evaluate an AST node adhering to strict limits."""
    if isinstance(node, ast.Constant):
        val = node.value
        # Reject booleans (bool is a subclass of int in Python)
        if isinstance(val, bool):
            raise CalculationError("Boolean literals are not allowed in calculator.")
        # Reject complex numbers
        if isinstance(val, complex):
            raise CalculationError("Complex numbers are not allowed in calculator.")
        if not isinstance(val, (int, float)):
            raise CalculationError(f"Unsupported constant type: {type(val).__name__}.")
        if abs(val) > MAX_NUMERIC_LITERAL:
            raise CalculationError(
                f"Numeric literal {val} exceeds maximum allowed magnitude ({MAX_NUMERIC_LITERAL})."
            )
        return float(val)

    if isinstance(node, ast.UnaryOp):
        operand = _safe_eval_ast(node.operand)
        if isinstance(node.op, ast.USub):
            res = -operand
        elif isinstance(node.op, ast.UAdd):
            res = +operand
        else:
            raise CalculationError(f"Unsupported unary operator: {type(node.op).__name__}.")

        if not math.isfinite(res) or abs(res) > MAX_RESULT_MAGNITUDE:
            raise CalculationError("Unary result exceeds maximum allowed magnitude.")
        return float(res)

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            base = _safe_eval_ast(node.left)
            exp = _safe_eval_ast(node.right)
            if abs(exp) > MAX_EXPONENT_MAGNITUDE:
                raise CalculationError(
                    f"Exponent magnitude {abs(exp)} exceeds maximum allowed ({MAX_EXPONENT_MAGNITUDE})."
                )
            try:
                res = base ** exp
            except OverflowError:
                raise CalculationError("Exponentiation overflow.")
        else:
            left = _safe_eval_ast(node.left)
            right = _safe_eval_ast(node.right)

            if isinstance(node.op, ast.Add):
                res = left + right
            elif isinstance(node.op, ast.Sub):
                res = left - right
            elif isinstance(node.op, ast.Mult):
                res = left * right
            elif isinstance(node.op, ast.Div):
                if right == 0.0:
                    raise CalculationError("Division by zero.")
                res = left / right
            elif isinstance(node.op, ast.FloorDiv):
                if right == 0.0:
                    raise CalculationError("Floor division by zero.")
                res = left // right
            elif isinstance(node.op, ast.Mod):
                if right == 0.0:
                    raise CalculationError("Modulo by zero.")
                res = left % right
            else:
                raise CalculationError(f"Unsupported binary operator: {type(node.op).__name__}.")

        if not math.isfinite(res):
            raise CalculationError("Calculation produced non-finite value (inf or nan).")
        if abs(res) > MAX_RESULT_MAGNITUDE:
            raise CalculationError(
                f"Calculation result {res} exceeds maximum allowed magnitude ({MAX_RESULT_MAGNITUDE})."
            )
        return float(res)

    raise CalculationError(f"Unsupported AST node type: {type(node).__name__}.")


def calculate(expression: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Safely calculate an arithmetic expression using restricted AST parsing.

    Args:
        expression: Mathematical expression string.
        context: Optional execution context.

    Returns:
        dict containing 'expression' and 'result'.
    """
    if not isinstance(expression, str):
        raise CalculationError("Expression must be a string.")

    cleaned = expression.strip()
    if not cleaned:
        raise CalculationError("Expression cannot be empty.")
    if len(cleaned) > MAX_EXPRESSION_LENGTH:
        raise CalculationError(
            f"Expression length ({len(cleaned)}) exceeds limit of {MAX_EXPRESSION_LENGTH} characters."
        )

    try:
        parsed = ast.parse(cleaned, mode="eval")
    except SyntaxError as e:
        raise CalculationError(f"Invalid arithmetic syntax: {e}") from e

    # Check for chained exponentiation (e.g., 9 ** 9 ** 9)
    _check_nested_exponentiation(parsed)

    # Safe AST evaluation
    result_val = _safe_eval_ast(parsed.body)

    return {
        "expression": cleaned,
        "result": float(result_val),
    }


# Registry of available local tools
LOCAL_TOOL_REGISTRY: dict[str, Callable[..., dict[str, Any]]] = {
    "read_file": read_file,
    "write_file": write_file,
    "calculate": calculate,
}


def dispatch_local_tool(
    tool_name: str,
    arguments: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch a tool call to a registered local tool implementation.

    Args:
        tool_name: Name of tool to execute.
        arguments: Keyword arguments for the tool.
        context: Standard execution context dictionary.

    Returns:
        Result data dictionary from the tool handler.
    """
    if tool_name not in LOCAL_TOOL_REGISTRY:
        raise LocalToolError(f"Tool '{tool_name}' is not in local tool registry.")

    handler = LOCAL_TOOL_REGISTRY[tool_name]

    if tool_name == "read_file":
        if "path" not in arguments:
            raise LocalToolError("Missing required argument 'path' for 'read_file'.")
        return handler(path=arguments["path"], context=context)

    if tool_name == "write_file":
        if "path" not in arguments or "content" not in arguments:
            raise LocalToolError("Missing required arguments ('path', 'content') for 'write_file'.")
        return handler(path=arguments["path"], content=arguments["content"], context=context)

    if tool_name == "calculate":
        if "expression" not in arguments:
            raise LocalToolError("Missing required argument 'expression' for 'calculate'.")
        return handler(expression=arguments["expression"], context=context)

    # Fallback generic dispatch
    return handler(**arguments, context=context)
