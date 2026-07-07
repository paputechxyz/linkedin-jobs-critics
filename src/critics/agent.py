"""opencode agent handoff primitives for the judge→fix→re-judge loop.

These helpers isolate the agent-side concerns (sibling-repo path resolution,
handoff-prompt construction, interactive opencode launch, session capture)
from the loop orchestration in `cli.py`. They are plain functions so they
can be unit-tested without a real opencode or a real sibling repo.
"""

from __future__ import annotations

import json
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


def build_handoff_prompt(report: CritiqueReport, round_num: int = 1) -> str:
    """Assemble the prompt handed to the opencode agent for a given round.

    Round 1 produces the full initial prompt (job context + every inconsistent
    finding + the `just build` rebuild instruction). Rounds 2+ assume the same
    opencode session is being resumed, so the agent already has the full
    transcript of prior rounds — the prompt is a concise follow-up naming only
    the fields the latest re-judge still flags as inconsistent, plus a nudge to
    try a different approach and rebuild again.

    Inlining the defects (rather than referencing a plan file in another repo)
    avoids the cross-directory working-directory problem: the agent runs in the
    sibling repo while the plan file lives in critics' cwd.
    """
    inconsistent = [f for f in report.findings if not f.is_consistent]

    if round_num == 1:
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
        return "\n".join(lines)

    # Follow-up for a resumed session — the agent remembers prior rounds.
    lines = [
        f"Round {round_num}: critics re-judged the job after the previous "
        f"agent round, and these fields are STILL inconsistent with the "
        f"description:",
        "",
    ]
    for f in inconsistent:
        lines.append(f"- {f.field}: stored '{f.stored_value}'")
        lines.append(f"  evidence (from description): {f.evidence_quote}")
        if f.suggested_fix:
            lines.append(f"  suggested fix location: {f.suggested_fix}")
    lines.append("")
    lines.append(
        "The previous approach did not fully resolve these — try a different "
        "fix, then REBUILD via `just build` (NOT plain `go build`). Do not commit."
    )
    return "\n".join(lines)


def launch_agent_session(
    repo_path: Path, prompt: str, session_id: str | None = None
) -> int:
    """Launch an interactive opencode TUI session in `repo_path` with `prompt`
    as the opening message.

    When `session_id` is None (round 1), starts a new session. When provided
    (rounds 2+), resumes that session with `--session <id>` so the agent keeps
    its full transcript; `--prompt` is sent as the new message into the resumed
    session.

    Inherits stdin/stdout/stderr (no capture_output) so the opencode TUI takes
    over the terminal and the user can supervise the agent live. Returns the
    opencode exit code. Blocks until the user exits opencode.
    """
    args = ["opencode", str(repo_path)]
    if session_id:
        args += ["--session", session_id]
    args += ["--prompt", prompt]
    return subprocess.run(args).returncode


def latest_session_id(repo_path: Path) -> str | None:
    """Return the most recent opencode session id whose directory matches
    `repo_path`, or None if no such session exists or the list call fails.

    Used after round 1's session exits to capture the id so rounds 2+ can
    resume it via `launch_agent_session(..., session_id=...)`.
    """
    proc = subprocess.run(
        ["opencode", "session", "list", "-n", "10", "--format", "json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if proc.returncode != 0:
        return None
    try:
        sessions = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    target = str(repo_path)
    for s in sessions:
        if s.get("directory") == target and s.get("id"):
            return s["id"]
    return None
