"""Terminal chat with an agent: make chat AGENT=triage TENANT=T-003 NOW=2026-01-14T19:30:00

Works on data/chat.db, copied fresh from data/harbour.db at start, so tickets
persist for the session. Each message is a separate run: the agent has no memory of
earlier messages.
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.tracers.langchain import wait_for_all_tracers

from app.models import RunRecord, TriageInput
from app.registry import AGENTS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TEMPLATE_DB = DATA_DIR / "harbour.db"
CHAT_DB = DATA_DIR / "chat.db"


def print_record(record: RunRecord) -> None:
    if record.error:
        print(f"\n  error: {record.error}")
    if record.result:
        print(f"\nagent> {record.result.reply}\n")
        print(f"  {'category':<12}{'priority':<11}ticket")
        for issue in record.result.issues or []:
            print(f"  {issue.category:<12}{issue.priority:<11}{issue.ticket}")
        if not record.result.issues:
            print("  (no issues)")
        print(f"  cited: {', '.join(record.result.cited_clauses) or '-'}")
    for ticket in record.tickets_created:
        paged = ", PAGED on-call" if ticket.paged_on_call else ""
        print(f"  created {ticket.id}: {ticket.priority} {ticket.category}{paged}")
    tools = " -> ".join(record.tool_calls) or "-"
    errors = f" ({record.tool_errors} tool errors)" if record.tool_errors else ""
    print(f"  tools: {tools}{errors}\n")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", choices=sorted(AGENTS), default="triage")
    parser.add_argument("--tenant", default="T-003")
    parser.add_argument("--now", type=datetime.fromisoformat, default=datetime.now())
    parser.add_argument("--fail-create-ticket", action="store_true")
    args = parser.parse_args()

    shutil.copyfile(TEMPLATE_DB, CHAT_DB)
    run = AGENTS[args.agent]
    print(
        f"Chatting with {args.agent} as {args.tenant} "
        f"at {args.now:%Y-%m-%d %H:%M} on {CHAT_DB.name}."
    )
    print("Empty line or Ctrl-D to quit.\n")

    try:
        while message := input("you> ").strip():
            inp = TriageInput(
                message=message,
                tenant_id=args.tenant,
                now=args.now,
                fail_create_ticket=args.fail_create_ticket,
            )
            print_record(run(inp, str(CHAT_DB)))
    except (EOFError, KeyboardInterrupt):
        print()
    finally:
        wait_for_all_tracers()


if __name__ == "__main__":
    main()
