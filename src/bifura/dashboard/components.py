"""Reusable presentation components for the Bifura Streamlit dashboard.

Member 2 ownership. Implements visual display of execution traces, safety decisions,
sequence comparisons, deviations, incident intelligence, impact graphs, and verification.
"""

from typing import Any
import streamlit as st

from bifura.dashboard.loader import LoadedRun
from bifura.schemas.bundle import RunBundle
from bifura.schemas.models import DependencyEdge


def render_header(loaded_run: LoadedRun):
    """Render top header with run metadata, status badges, and fault injection tags."""
    bundle = loaded_run.bundle
    run = bundle.run

    status_val = getattr(run.status, "value", str(run.status)).lower()

    col_title, col_badges = st.columns([3, 2])

    with col_title:
        st.markdown(f"## {bundle.scenario_id.replace('_', ' ').title()}")
        st.caption(f"Run ID: `{run.run_id}` | Agent: `{run.agent_name} v{run.agent_version}`")

    with col_badges:
        source_label = "📦 FIXTURE" if loaded_run.source_type == "fixture" else "⚡ RUNTIME"
        status_colors = {
            "succeeded": ":green",
            "blocked": ":red",
            "failed": ":orange",
            "pending": ":gray",
        }
        color = status_colors.get(status_val, ":gray")
        st.markdown(f"### {color}[{status_val.upper()}] `{source_label}`")
        if bundle.scenario_id in {"stale_state", "wrong_sequence"} or "deterministic_fault_injection" in run.tags:
            st.caption("Controlled Fault Injection: Deterministic Planner (No LLM)")

    # Summary box
    with st.container(border=True):
        st.markdown("#### 🎯 Task Description & Outcome")
        st.markdown(f"**Task:** {run.task_text or 'No task text provided'}")
        st.markdown(f"**Expected:** {run.expected_outcome or 'Not specified'}")
        st.markdown(f"**Actual Execution Summary:** {bundle.actual_execution_summary or run.actual_behavior or 'No summary recorded'}")


def render_sequence_comparison(bundle: RunBundle):
    """Render side-by-side comparison of expected vs actual tool action sequences."""
    expected_seq = bundle.expected_action_sequence or []

    # Derive actual proposed sequence from events
    actual_seq = [
        ev.tool_name
        for ev in bundle.events
        if ev.event_type == "tool_proposed" and ev.tool_name
    ]

    col_exp, col_act = st.columns(2)

    with col_exp:
        with st.container(border=True):
            st.markdown("#### 📋 Expected Action Sequence")
            if expected_seq:
                step_text = " ➔ ".join([f"`{tool}`" for tool in expected_seq])
                st.markdown(step_text)
            else:
                st.info("Not available for this run")

    with col_act:
        with st.container(border=True):
            match_status = "✅ MATCH" if expected_seq == actual_seq else "⚠️ DEVIATED"
            st.markdown(f"#### ⚡ Actual Proposed Sequence ({match_status})")
            if actual_seq:
                step_text = " ➔ ".join([f"`{tool}`" for tool in actual_seq])
                st.markdown(step_text)
            else:
                st.info("No tool actions proposed")


def render_event_timeline(bundle: RunBundle):
    """Render an ordered timeline of trace events using safe, native Streamlit components."""
    st.markdown("### ⏱️ Ordered Event Timeline")
    events = sorted(bundle.events, key=lambda e: e.sequence)

    if not events:
        st.info("No events recorded for this run.")
        return

    actor_colors = {
        "agent": ":violet",
        "safety_engine": ":red",
        "tool": ":green",
        "evaluator": ":orange",
        "system": ":gray",
    }

    for ev in events:
        with st.container(border=True):
            col_info, col_time = st.columns([5, 1])
            with col_info:
                color = actor_colors.get(ev.actor.lower(), ":blue")
                actor_badge = f"{color}[[{ev.actor.upper()}]]"
                tool_part = f" • Tool: `{ev.tool_name}`" if ev.tool_name else ""
                st.markdown(f"**#{ev.sequence} {ev.event_type}** `{ev.event_id}` {actor_badge}{tool_part}")
                if ev.summary:
                    st.caption(ev.summary)
            with col_time:
                st.caption(f"🕒 {ev.timestamp.strftime('%H:%M:%S.%f')[:-3]}")

            if ev.error:
                st.error(f"{ev.error_type or 'Error'}: {ev.error}")

            with st.expander(f"Inspect Event #{ev.sequence} ({ev.event_id}) Data", expanded=False):
                col_in, col_out = st.columns(2)
                with col_in:
                    st.markdown("**Input Data / Arguments:**")
                    st.json(ev.input_data or {})
                with col_out:
                    st.markdown("**Output / Error Data:**")
                    st.json(ev.output_data or {})


def render_safety_and_tools(bundle: RunBundle):
    """Render safety decisions and tool execution results using native components."""
    st.markdown("### 🛡️ Safety Decisions & Enforcement")

    if not bundle.safety_decisions:
        st.info("No safety decisions recorded for this run.")
    else:
        for dec in bundle.safety_decisions:
            dec_type = getattr(dec.decision, "value", str(dec.decision))
            with st.container(border=True):
                col_dec, col_id = st.columns([3, 2])
                with col_dec:
                    if dec_type == "ALLOW":
                        st.success(f"**ALLOW** — Policy Rule: `{dec.policy_rule}`")
                    elif dec_type == "BLOCK":
                        st.error(f"**BLOCK** — Policy Rule: `{dec.policy_rule}`")
                    else:
                        st.warning(f"**REVIEW** — Policy Rule: `{dec.policy_rule}`")
                with col_id:
                    st.caption(f"Decision ID: `{dec.decision_id}`")

                st.markdown(f"**Reason:** {dec.reason}")
                if dec.validated_target:
                    st.markdown(f"**Validated Target:** `{dec.validated_target}`")
                st.caption(
                    f"Execution Status: `{getattr(dec.execution_status, 'value', str(dec.execution_status))}` | "
                    f"Review Status: `{dec.review_status}`"
                )

    st.markdown("### ⚙️ Tool Execution Results")
    if not bundle.execution_results:
        st.info("No tool execution results recorded for this run.")
    else:
        for res in bundle.execution_results:
            with st.container(border=True):
                col_prop, col_status = st.columns([3, 2])
                with col_prop:
                    st.markdown(f"**Proposal:** `{res.proposal_id}`")
                with col_status:
                    success_badge = "✅ SUCCESS" if res.success else "❌ FAILED" if res.success is False else "⚪ UNKNOWN"
                    st.markdown(f"**Outcome:** {success_badge} (Executed: `{res.executed}`)")

                if res.error_message:
                    st.error(f"{res.error_type or 'Execution Error'}: {res.error_message}")
                if res.result_data:
                    with st.expander("Result Data", expanded=False):
                        st.json(res.result_data)


def render_deviation_analysis(bundle: RunBundle):
    """Render first deviation analysis, observed behaviors, and evidence using native components."""
    st.markdown("### 🔍 Deviation & Invariant Analysis")
    dev = bundle.deviation

    if dev is None:
        st.info("Not available for this run")
        return

    if not dev.found:
        st.success("✅ No deviation detected — execution conformed to expected behavior.")
        return

    with st.container(border=True):
        st.error(f"⚠️ **Observed Deviation Detected**: {dev.description or 'Deviation identified'}")
        st.markdown(f"**First Deviation Event ID:** `{dev.first_deviation_event_id or 'N/A'}`")
        st.markdown(f"**Expected Behavior:** {dev.expected_behavior or 'N/A'}")
        st.markdown(f"**Observed Behavior:** {dev.observed_behavior or 'N/A'}")
        if dev.explanation:
            st.info(f"**Explanation:** {dev.explanation}")


def render_incident_intelligence(bundle: RunBundle):
    """Render failure category predictions and historical incident retrieval matches using native components."""
    st.markdown("### 🧠 Incident Memory & Prediction")

    pred = bundle.prediction
    matches = bundle.incident_matches
    incidents = bundle.incident_records

    if pred is None and matches is None and incidents is None:
        st.info("Incident intelligence not available for this run.")
        return

    # Diagnosed Incident Records (Honesty Invariant Visibility)
    if incidents:
        st.markdown("#### 📋 Diagnosed Incident Record(s)")
        for inc in incidents:
            with st.container(border=True):
                col_i1, col_i2 = st.columns([3, 2])
                with col_i1:
                    st.markdown(f"**Incident ID:** `{inc.incident_id}`")
                    st.markdown(f"**Category:** `{getattr(inc.failure_category, 'value', str(inc.failure_category))}`")
                    st.caption(f"Observed Pattern: `{inc.observed_pattern}`")
                with col_i2:
                    status_text = f"Status: `{inc.label_status}`"
                    elig_text = "✅ Training Eligible" if inc.training_eligible else "❌ Training Ineligible"
                    if inc.training_eligible:
                        st.success(elig_text)
                    else:
                        st.warning(elig_text)
                    st.caption(status_text)
                if inc.root_cause_summary:
                    st.info(f"**Root Cause:** {inc.root_cause_summary}")

    col_pred, col_matches = st.columns(2)

    with col_pred:
        st.markdown("#### Failure Category Prediction")
        if pred is None:
            st.info("No prediction generated for this run.")
        else:
            meaning = pred.score_meaning
            with st.container(border=True):
                st.markdown(f"**Model:** `{pred.model_version}` ({pred.prediction_mode})")
                st.markdown(f"**Predicted Categories:** `{', '.join(pred.predicted_categories)}`")
                st.caption(f"Score Type: `{meaning}`")

            # Format prediction scores strictly according to score_meaning
            for cat, score in pred.scores.items():
                if meaning == "heuristic_support_score":
                    st.info(f"🏷️ **{cat}**: Heuristic Support Score `{score:.2f}` / 1.0 *(heuristic rules, non-probabilistic)*")
                elif meaning == "probability":
                    st.metric(label=f"Probability ({cat})", value=f"{score * 100:.1f}%")
                else:
                    st.metric(label=f"Score ({cat})", value=f"{score:.2f}")

    with col_matches:
        st.markdown("#### Historical Incident Matches")
        if not matches:
            st.info("No matching historical incidents retrieved.")
        else:
            for match in matches:
                with st.container(border=True):
                    col_m1, col_m2 = st.columns([3, 2])
                    with col_m1:
                        st.markdown(f"**Incident:** `{match.incident_id}`")
                    with col_m2:
                        st.markdown(f"**Similarity:** `{match.similarity_score:.2f}`")
                    st.write(match.match_reason)
                    if match.matched_features:
                        st.caption(f"Features: {', '.join(match.matched_features)}")


def render_impact_graph(bundle: RunBundle):
    """Render the causal impact graph supplied by Member 1 without inventing edges."""
    st.markdown("### 🕸️ Causal Impact Graph")
    graph = bundle.impact_graph

    if graph is None:
        st.info("Causal impact graph not available for this run.")
        return

    nodes = graph.nodes or []
    edges = graph.edges or []

    if not nodes and not edges:
        st.info("Causal impact graph is empty for this run.")
        return

    # Build Graphviz DOT representation from supplied edges
    dot_lines = [
        "digraph ImpactGraph {",
        "  rankdir=LR;",
        '  bgcolor="transparent";',
        '  node [shape=box, style="filled,rounded", fillcolor="#1E293B", fontcolor="#F8FAFC", color="#6366F1", fontname="Helvetica"];',
        '  edge [color="#818CF8", fontcolor="#CBD5E1", fontname="Helvetica", fontsize=10];',
    ]

    for n in nodes:
        nid = n.get("id") if isinstance(n, dict) else str(n)
        label = n.get("label") if isinstance(n, dict) else nid
        clean_label = str(label).replace('"', '\\"')
        dot_lines.append(f'  "{nid}" [label="{clean_label}"];')

    edge_details: list[dict[str, Any]] = []

    for e in edges:
        if isinstance(e, DependencyEdge):
            from_id = e.from_event_id
            to_id = e.to_event_id
            dep_type = e.dependency_type
            explanation = e.explanation
            status = getattr(e.evidence_status, "value", str(e.evidence_status))
        elif isinstance(e, dict):
            from_id = e.get("from_event_id")
            to_id = e.get("to_event_id")
            dep_type = e.get("dependency_type", "")
            explanation = e.get("explanation", "")
            status = e.get("evidence_status", "")
        else:
            continue

        if from_id and to_id:
            clean_dep = str(dep_type).replace('"', '\\"')
            dot_lines.append(f'  "{from_id}" -> "{to_id}" [label="{clean_dep}"];')
            edge_details.append(
                {
                    "from_event_id": from_id,
                    "to_event_id": to_id,
                    "dependency_type": dep_type,
                    "explanation": explanation,
                    "evidence_status": status,
                }
            )

    dot_lines.append("}")
    dot_str = "\n".join(dot_lines)

    st.graphviz_chart(dot_str)

    if edge_details:
        with st.expander("View Supplied Dependency Edges Table"):
            st.dataframe(edge_details)


def render_verification_report(bundle: RunBundle):
    """Render correction and replay verification report using native components."""
    st.markdown("### 🧪 Correction & Replay Verification")
    ver = bundle.verification

    if ver is None:
        st.info("No verification/replay report recorded for this run.")
        return

    status_badge = "✅ PASSED" if ver.passed else "❌ FAILED"
    with st.container(border=True):
        col_v1, col_v2 = st.columns([3, 2])
        with col_v1:
            if ver.passed:
                st.success(f"**Verification Status: {status_badge}**")
            else:
                st.error(f"**Verification Status: {status_badge}**")
        with col_v2:
            st.caption(f"Tests: {ver.total - ver.failures}/{ver.total} passed")

        st.write(ver.summary)
        st.caption(
            f"Replay Status: `{ver.replay_status}` | Targeted Test: `{ver.targeted_test_status}` | Regression Test: `{ver.regression_test_status}`"
        )
        if ver.command:
            st.code(ver.command, language="bash")
