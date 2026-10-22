# Bifura

Bifura is a prototype for incident-informed predictive debugging of multi-step AI-agent executions.

It aims to capture execution traces, identify evidence-supported deviations, retrieve relevant incidents, investigate possible causes, propose bounded fixes, and verify outcomes with tests and replay.

Safety enforcement is required implementation scope. Defining safety-decision data contracts alone does not implement enforcement.

## Requirements

- Python 3.11 or newer
- Git

## Windows setup

Run these commands from the repository root in Command Prompt:

```cmd
py -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Start the application

```cmd
streamlit run app.py
```

## Run tests

```cmd
python -m pytest -v
```

## Current implementation status

- Shared Pydantic contracts: initial implementation
- Initial contract tests: passing in the local environment; rerun before committing
- Agent tracing and investigation: not implemented yet
- Safety enforcement: not implemented yet
- Incident retrieval and prediction: not implemented yet
- Streamlit dashboard integration: not implemented yet
- Bounded patching and replay: not implemented yet

Features will be marked implemented only after they have been tested.

See `BIFURA_MASTER_PROJECT_SPEC.md` and `BIFURA_EXECUTION_PLAN.md` for the authoritative requirements and implementation order.