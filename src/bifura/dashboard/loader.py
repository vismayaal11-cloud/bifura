"""Run bundle loader and discovery for Bifura Streamlit dashboard.

Member 2 ownership. Scans and validates run bundles from both data/fixtures/ and data/runs/.
Handles missing runtime directories and malformed JSON files gracefully.
"""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from bifura.schemas.bundle import RunBundle


@dataclass
class LoadedRun:
    """Wrapper holding a validated RunBundle and its file provenance."""

    key: str
    bundle: RunBundle
    file_path: Path
    source_type: str  # "fixture" or "runtime"
    display_label: str


def discover_and_load_bundles(
    fixtures_dir: Path | str = "data/fixtures",
    runs_dir: Path | str = "data/runs",
) -> tuple[dict[str, LoadedRun], list[dict[str, Any]]]:
    """Discover, load, and validate all run bundles from fixtures and runtime directories.

    Returns:
        tuple of (loaded_runs_dict, errors_list)
        where loaded_runs_dict maps a unique key to a LoadedRun,
        and errors_list contains details of any files that failed validation.
    """
    loaded: dict[str, LoadedRun] = {}
    load_errors: list[dict[str, Any]] = []

    f_dir = Path(fixtures_dir)
    r_dir = Path(runs_dir)

    search_dirs = [
        (f_dir, "fixture"),
        (r_dir, "runtime"),
    ]

    for directory, source_type in search_dirs:
        # Runtime directory may not exist yet; handle that gracefully
        if not directory.exists() or not directory.is_dir():
            continue

        for file_path in sorted(directory.glob("*.json")):
            try:
                with file_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as exc:
                load_errors.append(
                    {
                        "file": str(file_path),
                        "source_type": source_type,
                        "error_type": "JSONDecodeError",
                        "error_message": f"Malformed JSON: {exc}",
                    }
                )
                continue
            except Exception as exc:
                load_errors.append(
                    {
                        "file": str(file_path),
                        "source_type": source_type,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    }
                )
                continue

            try:
                bundle = RunBundle.model_validate(data)
            except ValidationError as exc:
                load_errors.append(
                    {
                        "file": str(file_path),
                        "source_type": source_type,
                        "error_type": "ValidationError",
                        "error_message": f"RunBundle contract validation failed: {exc}",
                    }
                )
                continue

            scenario_name = bundle.scenario_id
            run_id = bundle.run.run_id
            status = getattr(bundle.run.status, "value", str(bundle.run.status))

            source_tag = "[FIXTURE]" if source_type == "fixture" else "[RUNTIME]"
            display_label = f"{source_tag} {scenario_name} ({run_id}) — {status.upper()}"
            key = f"{source_type}:{file_path.stem}:{run_id}"

            loaded[key] = LoadedRun(
                key=key,
                bundle=bundle,
                file_path=file_path,
                source_type=source_type,
                display_label=display_label,
            )

    return loaded, load_errors
