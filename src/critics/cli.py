"""critics - parsing-quality critic + human-gated judge→fix→re-judge loop.

Flow: look up the job by id in the local DB -> if missing, fetch + score it
via `linkedin-jobs score-job` -> judge the parsed fields against the
description -> write an improvement-plan MD. If defects are found, prompt the
user; on yes, launch an interactive opencode session in the sibling
linkedin-job-cli repo, then re-score + re-judge. Loop until clean or the user
stops. One-shot per job id; the loop is the agent round-trip.
"""

from __future__ import annotations

import argparse
import sys

from .agent import build_handoff_prompt, launch_agent_session, sibling_cli_dir
from .config import NoProviderError, load_llm
from .judge import CritiqueReport, judge_job
from .report import write_report
from .tools import cli_version, score_job, show_job


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


def _inconsistent(report: CritiqueReport) -> list:
    """Return the findings the judge flagged as inconsistent with the description."""
    return [f for f in report.findings if not f.is_consistent]


def _judge_and_write(job: dict, llm, out_path: str) -> CritiqueReport | None:
    """Judge the job and write its improvement plan. Returns the report, or
    None if judging failed (caller exits non-zero)."""
    print(f"Critics: judging job {job.get('id', '?')}...", file=sys.stderr)
    try:
        report = judge_job(job, llm)
    except Exception as e:  # structured-output / transport failure
        print(f"  ! judge failed: {e}", file=sys.stderr)
        return None
    write_report([report], out_path)
    return report


def _prompt_proceed() -> bool:
    """Ask whether to spawn the opencode agent for another round. Default no."""
    answer = input("Proceed to spawn opencode agent? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        llm = load_llm()
    except NoProviderError as e:
        print(str(e), file=sys.stderr)
        return 2

    print(f"Critics: looking up job {args.job_id} in DB...", file=sys.stderr)
    job = show_job(args.job_id)
    if job is None:
        print(
            f"  not stored; fetching via `linkedin-jobs score-job {args.job_id}`...",
            file=sys.stderr,
        )
        try:
            job = score_job(args.job_id)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1
    else:
        print("  found in DB.", file=sys.stderr)

    report = _judge_and_write(job, llm, args.out)
    if report is None:
        return 1
    print(f"Wrote {args.out}", file=sys.stderr)

    defects = _inconsistent(report)
    if not defects:
        print("No defects found; nothing to fix.", file=sys.stderr)
        return 0

    # judge→fix→re-judge loop, user-gated each round
    history: list[dict] = []
    while True:
        if not _prompt_proceed():
            print("Stopping; no agent spawned.", file=sys.stderr)
            return 0

        try:
            repo_path = sibling_cli_dir()
        except FileNotFoundError as e:
            print(str(e), file=sys.stderr)
            return 1

        version_before = cli_version()
        fields_attempted = [f.field for f in defects]
        print(
            f"Critics: launching opencode agent in {repo_path} "
            f"(round {len(history) + 1})...",
            file=sys.stderr,
        )
        launch_agent_session(repo_path, build_handoff_prompt(report, history))

        version_after = cli_version()
        if version_after == version_before or version_after == "dev":
            print(
                f"Critics: linkedin-jobs version unchanged after agent session "
                f"('{version_before}' -> '{version_after}'). The agent did not "
                f"rebuild via `just build`; skipping re-score. Stopping.",
                file=sys.stderr,
            )
            return 1

        print(
            f"Critics: re-scoring + re-judging job {args.job_id} "
            f"(version {version_before} -> {version_after})...",
            file=sys.stderr,
        )
        try:
            job = score_job(args.job_id)
        except RuntimeError as e:
            print(str(e), file=sys.stderr)
            return 1

        report = _judge_and_write(job, llm, args.out)
        if report is None:
            return 1

        new_defects = _inconsistent(report)
        history.append(
            {
                "round": len(history) + 1,
                "fields_attempted": fields_attempted,
                "fields_still_failing": [f.field for f in new_defects],
            }
        )

        if not new_defects:
            print(
                "Critics: re-judge clean — all defects resolved. Stopping.",
                file=sys.stderr,
            )
            return 0

        defects = new_defects
        # loop back: re-prompt with the fresh plan + accumulated history


if __name__ == "__main__":
    raise SystemExit(main())
