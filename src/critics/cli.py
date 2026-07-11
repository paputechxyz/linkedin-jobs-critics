"""critics - parsing-quality critic + human-gated judge→fix→re-judge loop.

Flow: look up the job by id in the local DB -> if missing, fetch + score it
via `linkedin-jobs score-job` -> judge the parsed fields against the
description -> write an improvement-plan MD. If defects are found, prompt the
user; on yes, launch an interactive opencode session in the sibling
linkedin-job-cli repo, then re-score + re-judge. Loop until clean or the user
stops. One-shot per job id; the loop is the agent round-trip.

The loop itself is implemented as a LangGraph state machine in `graph.py`;
this module owns arg parsing, the LLM config, the human-prompt, and the
invoke/resume driver.
"""

from __future__ import annotations

import argparse
import os
import sys

from langgraph.types import Command

from .config import NoProviderError, load_llm, setup_tracing
from .graph import build_graph


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="critics", description=__doc__)
    parser.add_argument(
        "job_id",
        help="LinkedIn job id to critique (e.g. 4259504707)",
    )
    parser.add_argument(
        "-o", "--out", default="improvement-plan.md", help="Output MD path"
    )
    return parser


def _prompt_proceed() -> bool:
    """Ask whether to spawn the opencode agent for another round. Default no."""
    answer = input("Proceed to spawn opencode agent? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if setup_tracing():
        project = (
            os.environ.get("LANGSMITH_PROJECT")
            or os.environ.get("LANGCHAIN_PROJECT")
            or "linkedin-jobs-critics"
        )
        print(f"Tracing enabled (LangSmith project: {project}).", file=sys.stderr)

    try:
        llm = load_llm()
    except NoProviderError as e:
        print(str(e), file=sys.stderr)
        return 2

    graph = build_graph()
    config = {
        "configurable": {
            "thread_id": f"critics-{args.job_id}-{os.getpid()}",
            "llm": llm,
        }
    }

    state = graph.invoke(
        {"job_id": args.job_id, "out_path": args.out}, config
    )

    # Drive the human gate: each time the graph pauses at `gate`, prompt the
    # user and resume with their decision. get_state().next is non-empty while
    # the graph is paused at an interrupt; it goes empty once a terminal node
    # has set rc and routed to END.
    while graph.get_state(config).next:
        decision = _prompt_proceed()
        state = graph.invoke(Command(resume=decision), config)

    return state.get("rc", 0)


if __name__ == "__main__":
    raise SystemExit(main())
