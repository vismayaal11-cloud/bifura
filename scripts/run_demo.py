#!/usr/bin/env python3
"""Minimal reproducible demo runner for Bifura hackathon demo.

Executes all four standardized scenarios end-to-end:
1. success:        read fixture -> calculate 15 * 4 = 60.0 -> write result to sandbox.
2. wrong_path:      block path traversal outside sandbox before any filesystem access.
3. stale_state:     policy allows actions, but assertion detects stale calculation input.
4. wrong_sequence:  distinguishes sequencing failure from safety block.

Enriches run bundles with incident memory and predictive diagnosis using real policy
and learning components. Offline, deterministic, no LLM required.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure src/ is on sys.path for direct execution
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from bifura.agent.scenarios import (
    DEMO_EXPECTED_ACTION_SEQUENCE,
    export_run_bundle,
    get_scenario_context,
    run_scenario,
)
from bifura.learning.loop import (
    enrich_run_bundle,
    load_incident_catalog,
    record_verification,
)
from bifura.learning.storage import IncidentStore
from bifura.repair.corrector import repair_wrong_path_and_replay
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import (
    FailureCategory,
    LabelStatus,
    SafetyDecisionType,
    utc_now,
)
from bifura.tools.policy import evaluate_tool_action


SCENARIOS = ["success", "wrong_path", "stale_state", "wrong_sequence"]


def ensure_sandbox_fixtures(repo_root: Path) -> None:
    """Ensure standard sandbox fixtures exist."""
    sandbox_fixtures = repo_root / "data" / "sandbox" / "fixtures"
    sandbox_fixtures.mkdir(parents=True, exist_ok=True)
    fixture_file = sandbox_fixtures / "scenario_1.txt"
    if not fixture_file.exists():
        fixture_file.write_text("15 * 4", encoding="utf-8")

    sandbox_runtime = repo_root / "data" / "sandbox" / "runtime"
    sandbox_runtime.mkdir(parents=True, exist_ok=True)


def init_incident_store(catalog_path: Path | str | None = None) -> IncidentStore:
    """Initialize an IncidentStore with historical catalog incidents."""
    store = IncidentStore()
    cat_path = Path(catalog_path) if catalog_path else REPO_ROOT / "data" / "incidents" / "catalog.json"
    if cat_path.exists():
        load_incident_catalog(cat_path, store)
    return store


def execute_demo_scenario(
    scenario_id: str,
    repo_root: Path | None = None,
    store: IncidentStore | None = None,
    output_dir: Path | None = None,
    repair: bool = False,
    clock: Any = utc_now,
) -> dict[str, Any]:
    """Execute a single scenario end-to-end, enrich with learning, and verify expectations."""
    root = repo_root or REPO_ROOT
    runs_dir = output_dir or (root / "data" / "runs")
    runs_dir.mkdir(parents=True, exist_ok=True)
    ensure_sandbox_fixtures(root)

    incident_store = store or init_incident_store(root / "data" / "incidents" / "catalog.json")

    # 1. Run scenario through real evaluate_tool_action and execute_tool_action
    bundle = run_scenario(
        scenario_id=scenario_id,
        repo_root=root,
        evaluator=evaluate_tool_action,  # Injected real policy evaluator
        clock=clock,
        export_bundle=False,  # Export after enrichment
    )

    # 2. Enrich run bundle with incident memory and failure prediction
    enriched_bundle = enrich_run_bundle(
        bundle=bundle,
        store=incident_store,
        clock=clock,
    )

    # 3. Optional bounded repair and replay for wrong_path scenario
    repaired_bundle = None
    verification_report = None
    if repair and scenario_id == "wrong_path":
        repaired_bundle, verification_report = repair_wrong_path_and_replay(
            baseline_bundle=enriched_bundle,
            repo_root=root,
            clock=clock,
        )
        if enriched_bundle.incident_records:
            inc_id = enriched_bundle.incident_records[0].incident_id
            updated_incident = record_verification(
                incident_id=inc_id,
                verification=verification_report,
                store=incident_store,
            )
            enriched_bundle = enriched_bundle.model_copy(
                update={
                    "incident_records": [updated_incident],
                    "verification": verification_report,
                }
            )

    # 4. Export enriched bundle to data/runs/{run_id}.json
    exported_path = export_run_bundle(enriched_bundle, output_dir=runs_dir)

    # 5. Build structured outcome summary
    decisions = [
        {
            "proposal_id": d.proposal_id,
            "decision": d.decision.value,
            "rule": d.policy_rule,
            "reason": d.reason,
            "execution_status": d.execution_status.value,
        }
        for d in enriched_bundle.safety_decisions
    ]

    exec_results = [
        {
            "proposal_id": r.proposal_id,
            "executed": r.executed,
            "success": r.success,
            "error_type": r.error_type,
            "result_data": r.result_data,
        }
        for r in enriched_bundle.execution_results
    ]

    deviation_info = None
    if enriched_bundle.deviation and enriched_bundle.deviation.found:
        deviation_info = {
            "first_deviation_event_id": enriched_bundle.deviation.first_deviation_event_id,
            "description": enriched_bundle.deviation.description,
            "expected_behavior": enriched_bundle.deviation.expected_behavior,
            "observed_behavior": enriched_bundle.deviation.observed_behavior,
        }

    diagnosis_info = None
    if enriched_bundle.incident_records:
        rec = enriched_bundle.incident_records[0]
        fc_val = rec.failure_category.value if hasattr(rec.failure_category, "value") else str(rec.failure_category)
        ls_val = rec.label_status.value if hasattr(rec.label_status, "value") else str(rec.label_status)
        diagnosis_info = {
            "incident_id": rec.incident_id,
            "failure_category": fc_val,
            "observed_pattern": rec.observed_pattern,
            "label_status": ls_val,
            "training_eligible": rec.training_eligible,
            "root_cause_summary": rec.root_cause_summary,
        }

    prediction_info = None
    if enriched_bundle.prediction:
        pred = enriched_bundle.prediction
        prediction_info = {
            "prediction_id": pred.prediction_id,
            "abstained": pred.abstained,
            "abstention_reason": pred.abstention_reason,
            "predicted_categories": [
                c.value if hasattr(c, "value") else str(c)
                for c in pred.predicted_categories
            ],
            "scores": pred.scores,
            "score_meaning": pred.score_meaning,
            "supporting_incident_ids": pred.supporting_incident_ids,
        }

    matches_info = [
        {
            "matched_incident_id": m.incident_id,
            "similarity_score": round(m.similarity_score, 3),
            "match_reason": m.match_reason,
        }
        for m in (enriched_bundle.incident_matches or [])
    ]

    # Verification of agreed scenario requirements
    validation_checks: dict[str, bool] = {}
    if scenario_id == "success":
        runtime_result = root / "data" / "sandbox" / "runtime" / "result.txt"
        file_matches = runtime_result.exists() and runtime_result.read_text(encoding="utf-8").strip() == "60.0"
        validation_checks = {
            "run_succeeded": enriched_bundle.run.status == "succeeded",
            "calculation_matches_60": file_matches,
            "no_deviation_found": not (enriched_bundle.deviation and enriched_bundle.deviation.found),
            "all_decisions_allow": all(d["decision"] == "ALLOW" for d in decisions),
            "prediction_abstained": enriched_bundle.prediction is not None and enriched_bundle.prediction.abstained,
        }
    elif scenario_id == "wrong_path":
        outside_file = root / "secrets.txt"
        validation_checks = {
            "run_blocked": enriched_bundle.run.status == "blocked",
            "outside_file_not_read": not outside_file.exists(),
            "tool_blocked_before_execution": any(
                d["decision"] == "BLOCK" and not r["executed"]
                for d, r in zip(decisions, exec_results)
            ),
            "deviation_detected": bool(enriched_bundle.deviation and enriched_bundle.deviation.found),
            "diagnosed_tool_input_validation": bool(
                diagnosis_info and diagnosis_info["failure_category"] == FailureCategory.TOOL_INPUT_VALIDATION.value
            ),
            "prediction_matched": bool(
                prediction_info and FailureCategory.TOOL_INPUT_VALIDATION.value in prediction_info["predicted_categories"]
            ),
        }
        if repair:
            validation_checks["repair_verified"] = bool(
                verification_report and verification_report.passed
            )
            validation_checks["training_eligible_after_verification"] = bool(
                diagnosis_info and diagnosis_info["training_eligible"]
            )
    elif scenario_id == "stale_state":
        validation_checks = {
            "run_failed": enriched_bundle.run.status == "failed",
            "safety_policy_allowed_actions": all(d["decision"] == "ALLOW" for d in decisions),
            "stale_input_first_deviation": bool(
                deviation_info and "Discrepancy" in (deviation_info["description"] or "")
            ),
            "diagnosed_state_or_dataflow": bool(
                diagnosis_info and diagnosis_info["failure_category"] == FailureCategory.STATE_OR_DATAFLOW.value
            ),
            "prediction_matched": bool(
                prediction_info and FailureCategory.STATE_OR_DATAFLOW.value in prediction_info["predicted_categories"]
            ),
            "training_not_eligible_unverified": bool(
                diagnosis_info and not diagnosis_info["training_eligible"]
            ),
        }
    elif scenario_id == "wrong_sequence":
        validation_checks = {
            "run_failed": enriched_bundle.run.status == "failed",
            "safety_policy_allowed_write": any(d["rule"] == "sandbox_containment" and d["decision"] == "ALLOW" for d in decisions),
            "precondition_first_deviation": bool(
                deviation_info and "Workflow precondition" in (deviation_info["description"] or "")
            ),
            "diagnosed_planning_or_tool_sequence": bool(
                diagnosis_info and diagnosis_info["failure_category"] == FailureCategory.PLANNING_OR_TOOL_SEQUENCE.value
            ),
            "prediction_matched": bool(
                prediction_info and FailureCategory.PLANNING_OR_TOOL_SEQUENCE.value in prediction_info["predicted_categories"]
            ),
            "training_not_eligible_unverified": bool(
                diagnosis_info and not diagnosis_info["training_eligible"]
            ),
        }

    all_passed = all(validation_checks.values())

    return {
        "scenario_id": scenario_id,
        "run_id": enriched_bundle.run.run_id,
        "status": enriched_bundle.run.status,
        "exported_file": str(exported_path),
        "all_passed": all_passed,
        "validation_checks": validation_checks,
        "decisions": decisions,
        "execution_results": exec_results,
        "deviation": deviation_info,
        "diagnosis": diagnosis_info,
        "prediction": prediction_info,
        "matches": matches_info,
        "verification_report": (
            {
                "passed": verification_report.passed,
                "summary": verification_report.summary,
                "tested_at": verification_report.tested_at.isoformat() if verification_report.tested_at else None,
            }
            if verification_report
            else None
        ),
        "bundle": enriched_bundle,
    }


def print_scenario_summary(result: dict[str, Any]) -> None:
    """Print readable terminal output for a demo scenario run."""
    scenario_id = result["scenario_id"]
    status = result["status"]
    passed_mark = "[PASS]" if result["all_passed"] else "[FAIL]"

    print(f"\n{'='*72}")
    print(f"  SCENARIO: {scenario_id.upper()}  |  STATUS: {status.upper()}  |  VERIFIED: {passed_mark}")
    print(f"{'='*72}")
    print(f"Run ID:        {result['run_id']}")
    print(f"Exported to:   {result['exported_file']}")

    print("\n-- Safety Decisions & Execution --")
    for i, (dec, exc) in enumerate(zip(result["decisions"], result["execution_results"]), start=1):
        executed_str = "EXECUTED (success)" if exc["success"] else ("NOT EXECUTED" if not exc["executed"] else "EXECUTION FAILED")
        print(f"  Step {i}: {dec['proposal_id']} -> Policy: {dec['decision']} ({dec['rule']}) | Executor: {executed_str}")
        if dec["decision"] == "BLOCK":
            print(f"          Reason: {dec['reason']}")

    if result["deviation"]:
        dev = result["deviation"]
        print("\n-- First-Deviation Analysis --")
        print(f"  Event ID:    {dev['first_deviation_event_id']}")
        print(f"  Description: {dev['description']}")
    else:
        print("\n-- First-Deviation Analysis --")
        print("  Zero deviations detected. Workflow conformed to expected action sequence.")

    if result["diagnosis"]:
        diag = result["diagnosis"]
        print("\n-- Incident Diagnosis (Member 3) --")
        print(f"  Category:          {diag['failure_category']}")
        print(f"  Observed Pattern:  {diag['observed_pattern']}")
        print(f"  Label Status:      {diag['label_status']}")
        print(f"  Training Eligible: {diag['training_eligible']} (Honesty Rule Enforced)")
        print(f"  Root Cause:        {diag['root_cause_summary']}")

    if result["prediction"]:
        pred = result["prediction"]
        print("\n-- Failure Prediction & Retrieval --")
        if pred["abstained"]:
            print(f"  Prediction: ABSTAINED")
            print(f"  Reason:     {pred['abstention_reason']}")
        else:
            print(f"  Predicted Category: {', '.join(pred['predicted_categories'])}")
            print(f"  Scores:             {pred['scores']} ({pred['score_meaning']})")
            if result["matches"]:
                print(f"  Retrieved Similar Incidents:")
                for m in result["matches"]:
                    print(f"    - {m['matched_incident_id']}: score={m['similarity_score']} ({m['match_reason']})")

    if result["verification_report"]:
        vr = result["verification_report"]
        print("\n-- Bounded Repair & Verification Replay --")
        print(f"  Passed:  {vr['passed']}")
        print(f"  Summary: {vr['summary']}")

    print("\n-- Acceptance Checklist --")
    for check_name, check_val in result["validation_checks"].items():
        box = "[x]" if check_val else "[ ]"
        print(f"  {box} {check_name}")


def main() -> int:
    """CLI entry point for the Bifura demo runner."""
    parser = argparse.ArgumentParser(
        description="Bifura Hackathon Demo Runner — Minimal Reproducible Integration Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--scenario",
        choices=["all", *SCENARIOS],
        default="all",
        help="Scenario to run (default: 'all')",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Execute bounded repair and replay on wrong_path scenario to verify fix",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data" / "runs",
        help="Directory to save exported RunBundle JSON files (default: data/runs)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON summary",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose per-scenario output",
    )

    args = parser.parse_args()

    scenarios_to_run = SCENARIOS if args.scenario == "all" else [args.scenario]
    store = init_incident_store(REPO_ROOT / "data" / "incidents" / "catalog.json")

    results: list[dict[str, Any]] = []
    all_succeeded = True

    if not args.quiet and not args.json:
        print("\n" + "="*72)
        print("   BIFURA HACKATHON DEMO: INCIDENT-INFORMED AGENT SAFETY & PREDICTION")
        print("="*72)
        print(f"Target Scenarios:  {', '.join(scenarios_to_run)}")
        print(f"Output Directory:  {args.output_dir}")
        print(f"Repair Enabled:    {args.repair}")
        print(f"Real Evaluator:    evaluate_tool_action (bifura.tools.policy)")
        print(f"Real Executor:     execute_tool_action (bifura.tools.executor)")
        print(f"Learning Store:    IncidentStore loaded with catalog.json")

    for sc in scenarios_to_run:
        res = execute_demo_scenario(
            scenario_id=sc,
            repo_root=REPO_ROOT,
            store=store,
            output_dir=args.output_dir,
            repair=args.repair,
        )
        results.append(res)
        if not res["all_passed"]:
            all_succeeded = False

        if not args.quiet and not args.json:
            print_scenario_summary(res)

    if args.json:
        serializable_results = [
            {k: v for k, v in r.items() if k != "bundle"}
            for r in results
        ]
        print(json.dumps(serializable_results, indent=2))
    elif not args.quiet:
        print("\n" + "="*72)
        print(f"   DEMO EXECUTION COMPLETE: {'ALL SCENARIOS PASSED' if all_succeeded else 'FAILURES DETECTED'}")
        print("="*72)
        print(f"Total Scenarios: {len(results)}")
        print(f"Passed:          {sum(1 for r in results if r['all_passed'])}")
        print(f"Failed:          {sum(1 for r in results if not r['all_passed'])}")
        print("Run bundles saved in: data/runs/")
        print("Launch Streamlit dashboard to inspect visually: streamlit run app.py\n")

    return 0 if all_succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
