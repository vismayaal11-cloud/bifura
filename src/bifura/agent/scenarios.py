"""Reproducible demo scenario execution and RunBundle export for Bifura."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from bifura.agent.agent import BifuraAgent
from bifura.analysis.deviation import detect_first_deviation
from bifura.analysis.impact import build_impact_graph
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    RunRecord,
    RunStatus,
    SafetyDecisionRecord,
    ToolCallProposal,
    utc_now,
)

# Canonical expected action sequence for demo scenarios
DEMO_EXPECTED_ACTION_SEQUENCE = ["read_file", "calculate", "write_file"]


def get_scenario_context(
    scenario_id: str,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build the standardized context dictionary for a demo scenario.

    Adheres strictly to Section 2.D Scenario Context Table of INTEGRATION_CONTRACT.md.
    Converts data/sandbox/ and data/sandbox/runtime/ to absolute paths.
    """
    root = Path(repo_root).resolve() if repo_root else Path.cwd().resolve()
    workspace_root = str((root / "data" / "sandbox").resolve())
    sandbox_root = str((root / "data" / "sandbox" / "runtime").resolve())

    # Permissions per scenario
    if scenario_id == "wrong_path":
        write_sandbox = False
    elif scenario_id in ("success", "stale_state", "wrong_sequence"):
        write_sandbox = True
    else:
        write_sandbox = False

    return {
        "mode": "demo",
        "allowed_tools": ["read_file", "calculate", "write_file"],
        "permissions": {
            "allow_network": False,
            "write_sandbox": write_sandbox,
            "write_project": False,
        },
        "workspace_root": workspace_root,
        "sandbox_root": sandbox_root,
        "provenance": "trusted_orchestrator",
    }


def export_run_bundle(
    bundle: RunBundle,
    output_dir: Path | str | None = None,
) -> Path:
    """Validate and export a real RunBundle to data/runs/{run_id}.json.

    Args:
        bundle: Validated RunBundle instance.
        output_dir: Directory to save the bundle (defaults to 'data/runs').

    Returns:
        Path to the exported JSON file.
    """
    out_dir = Path(output_dir) if output_dir else Path("data/runs")
    out_dir.mkdir(parents=True, exist_ok=True)

    file_path = out_dir / f"{bundle.run.run_id}.json"
    data = bundle.model_dump(mode="json")

    with file_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return file_path


def run_scenario(
    scenario_id: str,
    context: dict[str, Any] | None = None,
    repo_root: Path | str | None = None,
    evaluator: Callable[[ToolCallProposal, dict[str, Any]], SafetyDecisionRecord] | None = None,
    clock: Callable[[], Any] = utc_now,
    id_generator: Callable[[], str] | None = None,
    export_bundle: bool = True,
    output_dir: Path | str | None = None,
    run_id: str | None = None,
) -> RunBundle:
    """Execute a complete demo scenario and produce a canonical RunBundle.

    Args:
        scenario_id: One of 'success', 'wrong_path', 'stale_state', 'wrong_sequence'.
        context: Optional custom execution context (defaults to standard context table).
        repo_root: Optional root path for resolving sandbox directories.
        evaluator: Optional policy evaluator callable.
        clock: Injected clock for deterministic timestamps.
        id_generator: Injected ID generator for deterministic IDs.
        export_bundle: Whether to save the bundle to data/runs/{run_id}.json.
        output_dir: Optional custom directory for exported bundles.
        run_id: Optional fixed run_id.

    Returns:
        Canonical RunBundle instance.
    """
    ctx = dict(context or get_scenario_context(scenario_id, repo_root=repo_root))
    ctx["_clock"] = clock

    # Ensure runtime scratch directory exists before execution
    sandbox_root_path = Path(ctx["sandbox_root"])
    sandbox_root_path.mkdir(parents=True, exist_ok=True)

    actual_run_id = run_id or f"run-{scenario_id}-{clock().strftime('%Y%m%d%H%M%S')}"

    agent = BifuraAgent(
        evaluator=evaluator,
        clock=clock,
        id_generator=id_generator,
    )

    task_text = f"Execute standard demo scenario: {scenario_id}"
    agent_result = agent.run(
        task_text=task_text,
        scenario_id=scenario_id,
        context=ctx,
        run_id=actual_run_id,
    )

    # First-deviation detection
    deviation = detect_first_deviation(
        run_id=actual_run_id,
        events=agent_result.events,
        expected_action_sequence=DEMO_EXPECTED_ACTION_SEQUENCE,
    )

    # Impact graph construction from explicit causal dependencies
    impact_graph = build_impact_graph(
        run_id=actual_run_id,
        events=agent_result.events,
    )

    now = clock()
    # Build RunRecord conforming to canonical schema
    run_record = RunRecord(
        run_id=actual_run_id,
        task_text=task_text,
        task_summary=f"Automated execution of scenario '{scenario_id}'",
        expected_outcome="All planned actions execute safely inside sandbox",
        status=agent_result.status,
        started_at=now,
        finished_at=now,
        created_at=now,
        agent_name="bifura_practice_agent",
        agent_version="0.1.0",
        event_ids=[e.event_id for e in agent_result.events],
        actual_behavior=agent_result.actual_execution_summary,
    )

    # Assemble canonical RunBundle
    bundle = RunBundle(
        schema_version="1.0",
        scenario_id=scenario_id,
        run=run_record,
        expected_action_sequence=DEMO_EXPECTED_ACTION_SEQUENCE,
        actual_execution_summary=agent_result.actual_execution_summary,
        events=agent_result.events,
        safety_decisions=agent_result.safety_decisions,
        execution_results=agent_result.execution_results,
        deviation=deviation,
        incident_matches=None,  # Null until Member 3 integrates
        incident_records=None,  # Null until Member 3 integrates
        prediction=None,        # Null until Member 3 integrates
        impact_graph=impact_graph,
        verification=None,      # Null until replay/correction passes
    )

    if export_bundle:
        export_run_bundle(bundle, output_dir=output_dir)

    return bundle
