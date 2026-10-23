"""Visual styling and theme injection for Bifura Streamlit dashboard.

Member 2 ownership. Provides rich dark-mode aesthetics, glassmorphism cards,
custom status pills, and responsive typography.
"""

DASHBOARD_CSS = """
<style>
/* Main Dashboard Typography and Background */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

code, pre, .mono-font {
    font-family: 'JetBrains Mono', monospace !important;
}

/* Glassmorphism Card Containers */
.bifura-card {
    background: rgba(30, 41, 59, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 16px;
    box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.3);
    backdrop-filter: blur(12px);
    transition: transform 0.15s ease, border-color 0.15s ease;
}

.bifura-card:hover {
    border-color: rgba(99, 102, 241, 0.4);
}

.bifura-card-header {
    font-size: 0.95rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #94A3B8;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Status Badges */
.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    text-transform: uppercase;
}

.badge-succeeded {
    background: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.35);
}

.badge-blocked {
    background: rgba(244, 63, 94, 0.15);
    color: #FB7185;
    border: 1px solid rgba(244, 63, 94, 0.35);
}

.badge-failed {
    background: rgba(245, 158, 11, 0.15);
    color: #FBBF24;
    border: 1px solid rgba(245, 158, 11, 0.35);
}

.badge-pending {
    background: rgba(148, 163, 184, 0.15);
    color: #CBD5E1;
    border: 1px solid rgba(148, 163, 184, 0.35);
}

.badge-fault-injection {
    background: rgba(168, 85, 247, 0.18);
    color: #C084FC;
    border: 1px solid rgba(168, 85, 247, 0.4);
    font-weight: 700;
}

.badge-fixture {
    background: rgba(59, 130, 246, 0.15);
    color: #60A5FA;
    border: 1px solid rgba(59, 130, 246, 0.35);
}

.badge-runtime {
    background: rgba(16, 185, 129, 0.15);
    color: #34D399;
    border: 1px solid rgba(16, 185, 129, 0.35);
}

/* Decision Pills */
.decision-allow {
    background: rgba(16, 185, 129, 0.2);
    color: #10B981;
    border: 1px solid #10B981;
    padding: 2px 10px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 0.85rem;
}

.decision-review {
    background: rgba(99, 102, 241, 0.2);
    color: #818CF8;
    border: 1px solid #6366F1;
    padding: 2px 10px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 0.85rem;
}

.decision-block {
    background: rgba(239, 68, 68, 0.2);
    color: #EF4444;
    border: 1px solid #EF4444;
    padding: 2px 10px;
    border-radius: 6px;
    font-weight: 700;
    font-size: 0.85rem;
}

/* Event Timeline Item */
.timeline-item {
    border-left: 2px solid rgba(99, 102, 241, 0.3);
    padding-left: 16px;
    margin-left: 12px;
    margin-bottom: 14px;
    position: relative;
}

.timeline-dot {
    position: absolute;
    left: -7px;
    top: 4px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #6366F1;
    border: 2px solid #0F172A;
}

/* Sequence step badge */
.sequence-step {
    display: inline-block;
    padding: 4px 10px;
    margin: 2px 4px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
}

.sequence-arrow {
    color: #6366F1;
    font-weight: bold;
    margin: 0 4px;
}

/* Neutral Unavailable Notice */
.not-available-box {
    padding: 14px 18px;
    background: rgba(255, 255, 255, 0.03);
    border: 1px dashed rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    color: #94A3B8;
    font-style: italic;
    font-size: 0.9rem;
    text-align: center;
}
</style>
"""


def inject_dashboard_styles():
    """Inject the custom CSS into the Streamlit app."""
    import streamlit as st

    st.markdown(DASHBOARD_CSS, unsafe_allow_html=True)
