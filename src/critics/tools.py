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


def header_tags(job_id: str) -> dict | None:
    """Return the authoritative workplace-type header tag for a job via
    `linkedin-jobs header-tags <id> --json`, or None on any CLI failure
    (non-zero exit, empty/non-JSON output). The returned dict carries the
    Voyager API's workplace_type_urns, work_remote_allowed, derived
    remote_type, and source. None means the check could not run — typically a
    missing LinkedIn session — and callers should treat it as a soft skip."""
    proc = _run(["header-tags", str(job_id), "--json"], timeout=60)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


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


def cli_version() -> str:
    """Return the linkedin-jobs binary's version string via `linkedin-jobs
    version`, stripped. Empty string on any CLI failure (non-zero exit / no
    stdout). Used by the agent loop to detect whether the binary was rebuilt
    between rounds."""
    proc = _run(["version"], timeout=30)
    return proc.stdout.strip()
