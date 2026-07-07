"""Subprocess wrappers around the linkedin-jobs Go CLI.

Single-job operations only: look up a stored job with `show`, or fetch + score
a fresh one with `score-job`. The judge is a plain function (not an agent) and
calls these helpers directly.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess


def binary() -> str:
    return os.environ.get("LJ_BIN_PATH") or shutil.which("linkedin-jobs") or "linkedin-jobs"


def _run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [binary(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def _parse_job(proc: subprocess.CompletedProcess[str]) -> dict | None:
    """Return the parsed job dict from a `show`/`score-job` JSON result, or
    None on any non-zero exit / empty / non-JSON output."""
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(data, list):
        return data[0] if data else None
    return data


def show_job(job_id: str) -> dict | None:
    """Return a stored job by id via `linkedin-jobs show <id> --json`, or None
    if it is not in the DB (or any CLI error)."""
    proc = _run(["show", str(job_id), "--json"], timeout=60)
    return _parse_job(proc)


def score_job(job_id: str) -> dict:
    """Fetch + score a single LinkedIn job by id via `linkedin-jobs score-job
    <id> --json`. Always (re-)fetches and (re-)scores. Raises RuntimeError on
    failure."""
    proc = _run(["score-job", str(job_id), "--json"], timeout=180)
    job = _parse_job(proc)
    if job is None:
        raise RuntimeError(
            f"linkedin-jobs score-job {job_id} failed "
            f"(exit {proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    return job
