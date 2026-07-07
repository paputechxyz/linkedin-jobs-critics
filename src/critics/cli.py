"""critics - one-shot parsing-quality critic for a single linkedin-jobs posting.

Flow: look up the job by id in the local DB -> if missing, fetch + score it
via `linkedin-jobs score-job` -> judge the parsed fields against the
description -> write an improvement-plan MD. One-shot; no loop.
"""

from __future__ import annotations

import argparse
import sys

from .config import NoProviderError, load_llm
from .judge import judge_job
from .report import write_report
from .tools import score_job, show_job


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

    print(f"Critics: judging job {args.job_id}...", file=sys.stderr)
    try:
        report = judge_job(job, llm)
    except Exception as e:  # structured-output / transport failure
        print(f"  ! judge failed: {e}", file=sys.stderr)
        return 1

    out = write_report([report], args.out)
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
