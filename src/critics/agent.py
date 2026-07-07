"""opencode agent handoff primitives for the judge→fix→re-judge loop.

These helpers isolate the agent-side concerns (sibling-repo path resolution,
handoff-prompt construction, interactive opencode launch) from the loop
orchestration in `cli.py`. They are plain functions so they can be unit-tested
without a real opencode or a real sibling repo.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .judge import CritiqueReport


def sibling_cli_dir() -> Path:
    """Resolve the linkedin-job-cli sibling repo path.

    Priority: `LJ_CLI_DIR` env var → `<cwd>/../linkedin-job-cli`. Consistent
    with `LJ_BIN_PATH` (`tools.binary`) and `LJ_CONFIG_DIR` (`config.config_dir`).

    Raises FileNotFoundError if the resolved path is not an existing directory —
    fail fast with a clear message rather than letting opencode fail opaquely.
    """
    env = os.environ.get("LJ_CLI_DIR")
    raw = Path(env) if env else Path.cwd() / ".." / "linkedin-job-cli"
    resolved = raw.resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(
            f"linkedin-job-cli repo not found at {resolved} "
            f"(set LJ_CLI_DIR to override)"
        )
    return resolved


def build_handoff_prompt(
    report: CritiqueReport, history: list[dict] | None = None
) -> str:
    """Assemble the opening prompt handed to the opencode agent.

    Inlines the job's inconsistent findings (field, stored value, evidence,
    suggested fix) so the agent does not need to read a file in another repo.
    Always includes an explicit rebuild instruction naming `just build` (a
    plain `go build` leaves the version stamp at "dev" and the loop will
    reject it). When `history` is non-empty, renders a prior-rounds block so
    the agent does not repeat approaches that already failed.

    Each history entry is a dict with optional keys: `round` (int),
    `fields_attempted` (list[str]), `fields_still_failing` (list[str]).
    """
    history = history or []
    inconsistent = [f for f in report.findings if not f.is_consistent]

    lines = [
        f"You are fixing parsing defects in the linkedin-jobs Go CLI "
        f"for job {report.job_id} ({report.title}).",
        "",
        "The following parsed fields are inconsistent with the job's full "
        "description (the ground truth):",
        "",
    ]
    for f in inconsistent:
        lines.append(f"- field: {f.field}")
        lines.append(f"  stored value: {f.stored_value}")
        lines.append(f"  evidence (from description): {f.evidence_quote}")
        if f.suggested_fix:
            lines.append(f"  suggested fix location: {f.suggested_fix}")
        lines.append("")

    lines.append(
        "Fix the parser source so these fields parse correctly, then REBUILD "
        "the binary via `just build` (NOT plain `go build`) so the version "
        "stamp updates. Do not commit; the user commits manually."
    )

    if history:
        lines.append("")
        lines.append("Prior rounds — do not repeat approaches that failed:")
        for h in history:
            attempted = ", ".join(h.get("fields_attempted", [])) or "(none)"
            still = ", ".join(h.get("fields_still_failing", [])) or "(none)"
            lines.append(
                f"- round {h.get('round', '?')}: attempted [{attempted}]; "
                f"still failing after re-judge: [{still}]"
            )

    return "\n".join(lines)


def launch_agent_session(repo_path: Path, prompt: str) -> int:
    """Launch an interactive opencode TUI session in `repo_path` with `prompt`
    as the opening message.

    Inherits stdin/stdout/stderr (no capture_output) so the opencode TUI takes
    over the terminal and the user can supervise the agent live. Returns the
    opencode exit code. Blocks until the user exits opencode.
    """
    return subprocess.run(
        ["opencode", str(repo_path), "--prompt", prompt],
    ).returncode
