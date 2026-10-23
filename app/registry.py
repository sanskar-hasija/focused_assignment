"""Every agent the CLI and evals can run, by name.

To add an agent: write one module with its graph and a run function that calls
app.run.run_agent, then add one entry here.
"""

from collections.abc import Callable

from app.agent import run_triage
from app.agent_v1 import run_triage_v1
from app.models import RunRecord, TriageInput

AGENTS: dict[str, Callable[[TriageInput, str], RunRecord]] = {
    "triage": run_triage,  # V0: one tool-calling loop
    "triage_v1": run_triage_v1,  # V1: fixed steps with a code gate
}
