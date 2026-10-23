"""The function evaluations call: one input in, one RunRecord (as JSON) out.

Each call runs on its own fresh copy of data/harbour.db, so runs never see each
other's tickets. `python -m app.eval_target` runs one sample.
"""

import json
import tempfile
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tracers.langchain import wait_for_all_tracers

from app import db
from app.models import TriageInput
from app.registry import AGENTS

TEMPLATE_DB = Path(__file__).resolve().parent.parent / "data" / "harbour.db"


def make_target(agent_name: str = "triage") -> Callable[[dict], dict]:
    """An eval target that runs the named agent from app.registry.AGENTS."""
    if agent_name not in AGENTS:
        raise ValueError(f"Unknown agent {agent_name!r}; choose from {sorted(AGENTS)}")
    run = AGENTS[agent_name]

    def target(inputs: dict) -> dict:
        inp = TriageInput.model_validate(inputs)
        with tempfile.TemporaryDirectory(prefix=f"{agent_name}-") as tmp:
            record = run(inp, db.fresh_copy(TEMPLATE_DB, tmp))
        return record.model_dump(mode="json")

    return target


target = make_target("triage")


def main() -> None:
    load_dotenv()
    sample = {
        "message": "weird eggy smell in the kitchen",
        "tenant_id": "T-003",
        "now": "2026-01-14T19:30:00",
    }
    print(json.dumps(target(sample), indent=2))
    wait_for_all_tracers()


if __name__ == "__main__":
    main()
