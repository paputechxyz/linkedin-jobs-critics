"""Subprocess wrappers around the linkedin-jobs Go CLI.

The search step is exposed as a langchain @tool for the search agent; the job
list is read directly by the orchestrator (the judge is a function, not an
agent, so it does not need a tool).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

from langchain.tools import tool


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


def fetch_jobs() -> list[dict]:
    """Read every stored job as JSON via `list --json`."""
    proc = _run(["list", "--json"], timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(
            f"linkedin-jobs list failed (exit {proc.returncode}): {proc.stderr.strip()[:500]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"linkedin-jobs list returned non-JSON: {e}") from e


@tool
def linkedin_jobs_search(
    keywords: str,
    location: str,
    extra_search_args: list[str] | None = None,
) -> str:
    """Search LinkedIn jobs and populate/refresh the local DB via the
    linkedin-jobs CLI. Force-overwrites jobs already stored (re-parses and
    re-scores them). Returns a compact JSON summary {"count": N, "ids": [...]}.
    Use this to run a search for the given keywords and location.

    If extra_search_args is provided, pass each string verbatim as an
    additional flag to the underlying CLI (e.g. ["--min-salary=200k",
    "--top=1"]). Do not interpret or modify them."""
    extra = list(extra_search_args or [])
    try:
        proc = _run(
            ["search", keywords, location, *extra, "--force-overwrite", "--json"],
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: linkedin-jobs search timed out after 180s"
    except FileNotFoundError:
        return "ERROR: linkedin-jobs binary not found on PATH (set LJ_BIN_PATH)"
    if proc.returncode != 0:
        return f"ERROR (exit {proc.returncode}): {proc.stderr.strip()[:2000]}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return f"ERROR: non-JSON output ({e}); head={proc.stdout[:500]!r}"
    return json.dumps({"count": len(data), "ids": [j.get("id") for j in data]})
