"""critics - one-shot parsing-quality critic for the linkedin-jobs CLI.

Flow: search agent (force-overwrite) -> read jobs as JSON -> judge each ->
write an improvement-plan MD. One-shot; no loop.
"""

from __future__ import annotations

import argparse
import shlex
import sys

from .config import NoProviderError, load_llm
from .judge import judge_job
from .report import write_report
from .search_agent import run_search
from .tools import fetch_jobs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="critics", description=__doc__)
    parser.add_argument(
        "keywords",
        nargs="?",
        default="Senior Software Engineer",
        help="Search keywords (default: 'Senior Software Engineer')",
    )
    parser.add_argument("location", help="Search location, e.g. 'Toronto'")
    parser.add_argument("-o", "--out", default="improvement-plan.md", help="Output MD path")
    parser.add_argument(
        "--search-args",
        default=None,
        metavar='"FLAGS"',
        help="Extra flags to pass through to `linkedin-jobs search`, as a single "
        "shell-style string (e.g. --search-args \"--min-salary 200k --top 1\")",
    )
    parser.add_argument(
        "--skip-search",
        action="store_true",
        help="Judge jobs already in the DB without running a new search",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        llm = load_llm()
    except NoProviderError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not args.skip_search:
        extra = shlex.split(args.search_args) if args.search_args else []
        print(f"Search agent: searching {args.keywords!r} @ {args.location!r}...", file=sys.stderr)
        if extra:
            print(f"  extra search flags: {extra}", file=sys.stderr)
        summary = run_search(llm, args.keywords, args.location, extra)
        print(summary, file=sys.stderr)

    jobs = fetch_jobs()
    if not jobs:
        print("No jobs in DB to critique.", file=sys.stderr)
        return 0

    print(f"Critics: judging {len(jobs)} job(s)...", file=sys.stderr)
    reports = []
    for j in jobs:
        try:
            reports.append(judge_job(j, llm))
        except Exception as e:  # structured-output / transport failure: warn and continue
            print(f"  ! {j.get('id')}: {e}", file=sys.stderr)

    out = write_report(reports, args.out)
    print(f"Wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
