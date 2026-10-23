"""Bifura Streamlit Dashboard entry point.

Member 2 ownership. Provides interactive visual inspection of agent execution traces,
safety policy decisions, sequence comparisons, failure predictions, and impact graphs.
"""

import streamlit as st

from bifura.dashboard.components import (
    render_deviation_analysis,
    render_event_timeline,
    render_header,
    render_impact_graph,
    render_incident_intelligence,
    render_safety_and_tools,
    render_sequence_comparison,
    render_verification_report,
)
from bifura.dashboard.loader import discover_and_load_bundles
from bifura.dashboard.styles import inject_dashboard_styles

st.set_page_config(
    page_title="Bifura — Agent Safety & Predictive Debugging",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply sleek dark-mode glassmorphism styling
inject_dashboard_styles()

# Load all valid run bundles from fixtures and runtime directories
loaded_runs, load_errors = discover_and_load_bundles(
    fixtures_dir="data/fixtures",
    runs_dir="data/runs",
)

# Sidebar setup
st.sidebar.markdown("## 🛡️ BIFURA")
st.sidebar.markdown(
    "<span style='color: #94A3B8; font-size: 0.85rem;'>Incident-Informed Predictive Debugging & Safety Governance</span>",
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")

if not loaded_runs:
    st.error("No run bundles found in `data/fixtures/` or `data/runs/`.")
    st.stop()

# Friendly reporting of any malformed files without crashing the app
if load_errors:
    with st.sidebar.expander(f"⚠️ Load Warnings ({len(load_errors)})", expanded=False):
        for err in load_errors:
            st.warning(f"**{err['file']}** ({err['error_type']}):\n{err['error_message']}")

# Run Selector
selected_key = st.sidebar.selectbox(
    "Select Run / Scenario:",
    options=list(loaded_runs.keys()),
    format_func=lambda k: loaded_runs[k].display_label,
    index=0,
)

selected_loaded_run = loaded_runs[selected_key]
bundle = selected_loaded_run.bundle

# Sidebar Metrics and Scenario Context
st.sidebar.markdown("### 📊 Workspace Statistics")
total_runs = len(loaded_runs)
fixture_count = sum(1 for r in loaded_runs.values() if r.source_type == "fixture")
runtime_count = sum(1 for r in loaded_runs.values() if r.source_type == "runtime")

col_s1, col_s2 = st.sidebar.columns(2)
col_s1.metric("Total Runs", total_runs)
col_s2.metric("Fixtures", fixture_count)

st.sidebar.markdown(f"**Current File:**\n`{selected_loaded_run.file_path}`")
st.sidebar.markdown("---")
st.sidebar.caption("Bifura Hackathon Foundation | Member 2: Safety & Frontend")

# Main Content Area
render_header(selected_loaded_run)
render_sequence_comparison(bundle)

tab_timeline, tab_safety, tab_dev, tab_graph, tab_incidents, tab_verification = st.tabs(
    [
        "⏱️ Timeline & Traces",
        "🛡️ Safety Decisions",
        "🔍 Deviation Analysis",
        "🕸️ Causal Impact Graph",
        "🧠 Incident & Prediction",
        "🧪 Verification & Replay",
    ]
)

with tab_timeline:
    render_event_timeline(bundle)

with tab_safety:
    render_safety_and_tools(bundle)

with tab_dev:
    render_deviation_analysis(bundle)

with tab_graph:
    render_impact_graph(bundle)

with tab_incidents:
    render_incident_intelligence(bundle)

with tab_verification:
    render_verification_report(bundle)
