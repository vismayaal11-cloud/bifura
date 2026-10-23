"""Tests for local tools: read_file, write_file, calculate, and security containment."""

import json
from pathlib import Path
import pytest

from bifura.tools.local_tools import (
    CalculationError,
    SecurityViolationError,
    calculate,
    dispatch_local_tool,
    read_file,
    write_file,
)


@pytest.fixture
def test_context(tmp_path: Path) -> dict:
    """Create isolated sandbox and workspace roots for testing."""
    workspace = tmp_path / "sandbox"
    runtime = workspace / "runtime"
    fixtures = workspace / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    runtime.mkdir(parents=True, exist_ok=True)

    # Write a test fixture
    (fixtures / "scenario_1.txt").write_text("15 * 4", encoding="utf-8")

    return {
        "mode": "demo",
        "workspace_root": str(workspace),
        "sandbox_root": str(runtime),
        "allowed_tools": ["read_file", "calculate", "write_file"],
        "permissions": {
            "allow_network": False,
            "write_sandbox": True,
            "write_project": False,
        },
        "provenance": "trusted_orchestrator",
    }


def test_read_file_success(test_context: dict):
    """Test reading an authorized file inside workspace_root."""
    result = read_file("fixtures/scenario_1.txt", context=test_context)
    assert result["content"] == "15 * 4"
    assert result["path"] == "fixtures/scenario_1.txt"
    assert result["bytes_read"] == 6


def test_read_file_not_found(test_context: dict):
    """Test reading a non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        read_file("fixtures/non_existent.txt", context=test_context)


def test_read_file_path_traversal_rejection(test_context: dict):
    """Test that path traversal attempts are rejected."""
    with pytest.raises(SecurityViolationError, match="strictly prohibited|resolves outside"):
        read_file("../secrets.txt", context=test_context)

    with pytest.raises(SecurityViolationError):
        read_file("fixtures/../../secrets.txt", context=test_context)


def test_read_file_forbidden_targets(test_context: dict):
    """Test that sensitive files like .env or .git are rejected."""
    with pytest.raises(SecurityViolationError):
        read_file(".env", context=test_context)

    with pytest.raises(SecurityViolationError):
        read_file(".git/config", context=test_context)


def test_read_file_windows_reserved_names(test_context: dict):
    """Test that Windows reserved names (CON, NUL, AUX, etc.) are rejected."""
    with pytest.raises(SecurityViolationError, match="reserved Windows device name"):
        read_file("CON.txt", context=test_context)

    with pytest.raises(SecurityViolationError, match="reserved Windows device name"):
        read_file("sub/NUL", context=test_context)


def test_read_file_colon_and_drive_rejection(test_context: dict):
    """Test that drive letters and alternate data streams are rejected."""
    with pytest.raises(SecurityViolationError):
        read_file("C:\\Windows\\system.ini", context=test_context)

    with pytest.raises(SecurityViolationError):
        read_file("test.txt:stream", context=test_context)


def test_write_file_success(test_context: dict):
    """Test writing a file inside sandbox_root with proper permissions."""
    result = write_file("result.txt", "60.0", context=test_context)
    assert result["path"] == "result.txt"
    assert result["bytes_written"] == 4

    # Verify content was written on disk
    written_file = Path(test_context["sandbox_root"]) / "result.txt"
    assert written_file.exists()
    assert written_file.read_text(encoding="utf-8") == "60.0"


def test_write_file_without_permission(test_context: dict):
    """Test writing fails when permissions['write_sandbox'] is False."""
    test_context["permissions"]["write_sandbox"] = False
    with pytest.raises(SecurityViolationError, match="write_sandbox"):
        write_file("result.txt", "60.0", context=test_context)


def test_write_file_path_traversal_rejection(test_context: dict):
    """Test writing outside sandbox_root is rejected."""
    with pytest.raises(SecurityViolationError):
        write_file("../escape.txt", "danger", context=test_context)


def test_dispatch_local_tool(test_context: dict):
    """Test dispatching tools through dispatch_local_tool."""
    res_read = dispatch_local_tool("read_file", {"path": "fixtures/scenario_1.txt"}, test_context)
    assert res_read["content"] == "15 * 4"

    res_calc = dispatch_local_tool("calculate", {"expression": "15 * 4"}, test_context)
    assert res_calc["result"] == 60.0

    res_write = dispatch_local_tool("write_file", {"path": "result.txt", "content": "60.0"}, test_context)
    assert res_write["bytes_written"] == 4


def test_calculator_all_shared_cases():
    """Verify all shared calculator test cases from calculator_cases.json."""
    cases_path = Path("tests/fixtures/calculator_cases.json")
    assert cases_path.exists(), "calculator_cases.json must exist"

    with cases_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    for case in data["cases"]:
        case_id = case["id"]
        expr = case["expression"]
        expected_valid = case["expected_valid"]
        expected_result = case["expected_result"]

        if expected_valid:
            res = calculate(expr)
            assert pytest.approx(res["result"]) == expected_result, f"Failed case {case_id}"
        else:
            with pytest.raises(CalculationError):
                calculate(expr)
