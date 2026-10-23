"""Bifura Streamlit dashboard package.

Member 2 ownership. Provides reusable dashboard components, run bundle loaders,
and visual aesthetics for interactive predictive debugging.
"""

from bifura.dashboard.loader import LoadedRun, discover_and_load_bundles

__all__ = [
    "LoadedRun",
    "discover_and_load_bundles",
]
