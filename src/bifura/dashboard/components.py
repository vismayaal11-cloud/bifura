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
    status_class = f"badge-{status_val}" if status_val in {"succeeded", "blocked", "failed", "pending"} else "badge-pending"

    col_title, col_badges = st.columns([3, 2])

    with col_title:
        st.markdown(f"## {bundle.scenario_id.replace('_', ' ').title()}")
        st.caption(f"Run ID: `{run.run_id}` | Agent: `{run.agent_name} v{run.agent_version}`")

    with col_badges:
        st.markdown("<div style='text-align: right; padding-top: 8px;'>", unsafe_allow_html=True)

        # Source badge (Fixture vs Runtime)
        source_cls = "badge-fixture" if loaded_run.source_type == "fixture" else "badge-runtime"
        source_label = "MOCK FIXTURE" if loaded_run.source_type == "fixture" else "REAL RUNTIME BUNDLE"
        st.markdown(f"<span class='badge {source_cls}'>{source_label}</span>", unsafe_allow_html=True)

        # Status badge
        st.markdown(f"<span class='badge {status_class}'>{status_val.upper()}</span>", unsafe_allow_html=True)

        # Controlled Fault Injection Badge for stale_state and wrong_sequence
        if bundle.scenario_id in {"stale_state", "wrong_sequence"} or "deterministic_fault_injection" in run.tags:
            st.markdown(
                "<span class='badge badge-fault-injection'>Controlled Fault Injection: Deterministic Planner (No LLM)</span>",
                unsafe_allow_html=True,
            )

        st.markdown("</div>", unsafe_allow_html=True)

    # Summary box
    st.markdown(
        f"""
        <div class="bifura-card">
            <div class="bifura-card-header">🎯 Task Description & Outcome</div>
            <div style="font-size: 1rem; margin-bottom: 6px;"><b>Task:</b> {run.task_text or 'No task text provided'}</div>
            <div style="color: #94A3B8; font-size: 0.9rem;"><b>Expected:</b> {run.expected_outcome or 'Not specified'}</div>
            <div style="color: #CBD5E1; font-size: 0.9rem; margin-top: 4px;"><b>Actual Execution Summary:</b> {bundle.actual_execution_summary or run.actual_behavior or 'No summary recorded'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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
        st.markdown(
            """
            <div class="bifura-card">
                <div class="bifura-card-header">📋 Expected Action Sequence</div>
            """,
            unsafe_allow_html=True,
        )
        if expected_seq:
            step_html = " <span class='sequence-arrow'>➔</span> ".join(
                [f"<span class='sequence-step'>{tool}</span>" for tool in expected_seq]
            )
            st.markdown(f"<div style='margin-top: 8px;'>{step_html}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_act:
        match_status = "✅ MATCH" if expected_seq == actual_seq else "⚠️ DEVIATED"
        st.markdown(
            f"""
            <div class="bifura-card">
                <div class="bifura-card-header">⚡ Actual Proposed Sequence ({match_status})</div>
            """,
            unsafe_allow_html=True,
        )
        if actual_seq:
            step_html = " <span class='sequence-arrow'>➔</span> ".join(
                [f"<span class='sequence-step'>{tool}</span>" for tool in actual_seq]
            )
            st.markdown(f"<div style='margin-top: 8px;'>{step_html}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='not-available-box'>No tool actions proposed</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


def render_event_timeline(bundle: RunBundle):
    """Render an ordered timeline of trace events."""
    st.markdown("### ⏱️ Ordered Event Timeline")
    events = sorted(bundle.events, key=lambda e: e.sequence)

    if not events:
        st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
        return

    actor_colors = {
        "agent": "#6366F1",
        "safety_engine": "#EC4899",
        "tool": "#10B981",
        "evaluator": "#F59E0B",
        "system": "#64748B",
    }

    for ev in events:
        actor_color = actor_colors.get(ev.actor, "#94A3B8")
        st.markdown(
            f"""
            <div class="timeline-item">
                <div class="timeline-dot" style="background: {actor_color};"></div>
                <div style="display: flex; align-items: center; gap: 8px; font-size: 0.9rem;">
                    <span style="font-weight: 700; color: #E2E8F0;">#{ev.sequence} {ev.event_type}</span>
                    <span class="mono-font" style="background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px; font-size: 0.75rem;">{ev.event_id}</span>
                    <span style="color: {actor_color}; font-weight: 600; font-size: 0.8rem;">[{ev.actor.upper()}]</span>
                    {f"<span style='color: #A5B4FC; font-weight: 600;'>Tool: {ev.tool_name}</span>" if ev.tool_name else ''}
                    <span style="color: #64748B; font-size: 0.75rem; margin-left: auto;">{ev.timestamp.strftime('%H:%M:%S.%f')[:-3]}</span>
                </div>
                <div style="color: #94A3B8; font-size: 0.85rem; margin-top: 4px;">{ev.summary or ''}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander(f"Inspect Event #{ev.sequence} ({ev.event_id}) Data", expanded=False):
            col_in, col_out = st.columns(2)
            with col_in:
                st.markdown("**Input Data / Arguments:**")
                st.json(ev.input_data or {})
            with col_out:
                st.markdown("**Output / Error Data:**")
                if ev.error:
                    st.error(f"{ev.error_type or 'Error'}: {ev.error}")
                st.json(ev.output_data or {})


def render_safety_and_tools(bundle: RunBundle):
    """Render safety decisions and tool execution results."""
    st.markdown("### 🛡️ Safety Decisions & Enforcement")

    if not bundle.safety_decisions:
        st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
    else:
        for dec in bundle.safety_decisions:
            dec_type = getattr(dec.decision, "value", str(dec.decision))
            pill_class = (
                "decision-allow"
                if dec_type == "ALLOW"
                else "decision-block"
                if dec_type == "BLOCK"
                else "decision-review"
            )

            st.markdown(
                f"""
                <div class="bifura-card">
                    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                        <span class="{pill_class}">{dec_type}</span>
                        <span class="mono-font" style="color: #94A3B8; font-size: 0.8rem;">Decision ID: {dec.decision_id}</span>
                    </div>
                    <div><b>Policy Rule:</b> <code>{dec.policy_rule}</code></div>
                    <div style="margin-top: 4px;"><b>Reason:</b> {dec.reason}</div>
                    {f"<div style='margin-top: 4px; color: #34D399;'><b>Validated Target:</b> <code>{dec.validated_target}</code></div>" if dec.validated_target else ''}
                    <div style="margin-top: 6px; font-size: 0.8rem; color: #64748B;">
                        Execution Status: <code>{getattr(dec.execution_status, 'value', str(dec.execution_status))}</code> | Review Status: <code>{dec.review_status}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("### ⚙️ Tool Execution Results")
    if not bundle.execution_results:
        st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
    else:
        for res in bundle.execution_results:
            success_badge = "✅ SUCCESS" if res.success else "❌ FAILED" if res.success is False else "⚪ UNKNOWN"
            st.markdown(
                f"""
                <div class="bifura-card">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
                        <span style="font-weight: 700;">Proposal: <code>{res.proposal_id}</code></span>
                        <span>{success_badge} (Executed: {res.executed})</span>
                    </div>
                    {f"<div style='color: #F87171;'><b>{res.error_type}:</b> {res.error_message}</div>" if res.error_message else ''}
                </div>
                """,
                unsafe_allow_html=True,
            )
            if res.result_data:
                st.json(res.result_data)


def render_deviation_analysis(bundle: RunBundle):
    """Render first deviation analysis, observed behaviors, and evidence."""
    st.markdown("### 🔍 Deviation & Invariant Analysis")
    dev = bundle.deviation

    if dev is None:
        st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
        return

    if not dev.found:
        st.success("✅ No deviation detected — execution conformed to expected behavior.")
        return

    st.markdown(
        f"""
        <div class="bifura-card" style="border-left: 4px solid #F43F5E;">
            <div class="bifura-card-header" style="color: #FB7185;">⚠️ Observed Deviation Detected</div>
            <div style="font-size: 1.05rem; font-weight: 600; margin-bottom: 8px;">{dev.description or 'Deviation identified'}</div>
            <div><b>First Deviation Event ID:</b> <code>{dev.first_deviation_event_id or 'N/A'}</code></div>
            <div style="margin-top: 6px;"><b>Expected Behavior:</b> {dev.expected_behavior or 'N/A'}</div>
            <div style="margin-top: 4px; color: #FB7185;"><b>Observed Behavior:</b> {dev.observed_behavior or 'N/A'}</div>
            {f"<div style='margin-top: 6px; font-style: italic; color: #94A3B8;'>{dev.explanation}</div>" if dev.explanation else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_incident_intelligence(bundle: RunBundle):
    """Render failure category predictions and historical incident retrieval matches."""
    st.markdown("### 🧠 Incident Memory & Prediction")

    pred = bundle.prediction
    matches = bundle.incident_matches

    if pred is None and matches is None and bundle.incident_records is None:
        st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
        return

    col_pred, col_matches = st.columns(2)

    with col_pred:
        st.markdown("#### Failure Category Prediction")
        if pred is None:
            st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
        else:
            meaning = pred.score_meaning
            st.markdown(
                f"""
                <div class="bifura-card">
                    <div class="bifura-card-header">Model: {pred.model_version} ({pred.prediction_mode})</div>
                    <div><b>Predicted Categories:</b> <code>{', '.join(pred.predicted_categories)}</code></div>
                    <div style="margin-top: 6px; font-size: 0.85rem; color: #94A3B8;">
                        Score Type: <code>{meaning}</code>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

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
            st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
        else:
            for match in matches:
                st.markdown(
                    f"""
                    <div class="bifura-card">
                        <div style="display: flex; justify-content: space-between;">
                            <span style="font-weight: 700;">Incident <code>{match.incident_id}</code></span>
                            <span style="color: #818CF8; font-weight: 600;">Similarity: {match.similarity_score:.2f}</span>
                        </div>
                        <div style="margin-top: 6px; font-size: 0.9rem;">{match.match_reason}</div>
                        {f"<div style='margin-top: 4px; font-size: 0.8rem; color: #94A3B8;'>Features: {', '.join(match.matched_features)}</div>" if match.matched_features else ''}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def render_impact_graph(bundle: RunBundle):
    """Render the causal impact graph supplied by Member 1 without inventing edges."""
    st.markdown("### 🕸️ Causal Impact Graph")
    graph = bundle.impact_graph

    if graph is None:
        st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
        return

    nodes = graph.nodes or []
    edges = graph.edges or []

    if not nodes and not edges:
        st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
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
        # ImpactGraph.edges may contain either DependencyEdge objects or plain dictionaries
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
    """Render correction and replay verification report when present."""
    st.markdown("### 🧪 Correction & Replay Verification")
    ver = bundle.verification

    if ver is None:
        st.markdown("<div class='not-available-box'>Not available for this run</div>", unsafe_allow_html=True)
        return

    status_badge = "✅ PASSED" if ver.passed else "❌ FAILED"
    st.markdown(
        f"""
        <div class="bifura-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: 700; font-size: 1.1rem;">Verification Status: {status_badge}</span>
                <span class="mono-font" style="color: #94A3B8;">Tests: {ver.total - ver.failures}/{ver.total} passed</span>
            </div>
            <div style="font-size: 0.95rem; margin-top: 4px;">{ver.summary}</div>
            <div style="margin-top: 8px; font-size: 0.85rem; color: #94A3B8;">
                Replay Status: <code>{ver.replay_status}</code> | Targeted Test: <code>{ver.targeted_test_status}</code> | Regression Test: <code>{ver.regression_test_status}</code>
            </div>
            {f"<div style='margin-top: 6px;'><b>Command:</b> <code>{ver.command}</code></div>" if ver.command else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )
