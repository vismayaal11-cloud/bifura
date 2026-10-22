
"""Bifura's initial Streamlit application."""

import streamlit as st

st.set_page_config(
    page_title="Bifura",
    page_icon="🔎",
    layout="wide",
)

st.title("Bifura")
st.subheader("Incident-informed predictive debugging for AI agents")

st.info(
    "Foundation stage: shared data contracts are available. "
    "Trace capture, investigation, incident prediction, safety "
    "enforcement, repair, and replay are not integrated yet."
)

st.markdown("### Current foundation")
st.markdown(
    """
    - Python environment and dependencies configured
    - Shared Pydantic contracts defined
    - Initial contract tests passing
    """
)

st.caption(
    "This is a startup scaffold, not a completed debugging system. "
    "Only verified functionality will be presented as implemented."
)
