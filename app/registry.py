"""Every agent the CLI and evals can run, by name.

To add an agent: write one module with its graph and a run function that calls
app.run.run_agent, then add one entry here.
"""

from collections.abc import Callable

from app.agent import run_triage
from app.models import RunRecord, TriageInput

AGENTS: dict[str, Callable[[TriageInput, str], RunRecord]] = {"triage": run_triage}
