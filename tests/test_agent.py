import json
import subprocess

import pytest

from critics import agent
from critics.agent import (
    build_handoff_prompt,
    launch_agent_session,
    latest_session_id,
    sibling_cli_dir,
)
from critics.judge import CritiqueReport, Finding


def _finding(field, consistent=False, suggested_fix=None):
    return Finding(
        field=field,
        stored_value=f"<stored {field}>",
        evidence_quote=f"<ev {field}>",
        is_consistent=consistent,
        suggested_fix=suggested_fix,
    )


def _report(findings):
    return CritiqueReport(job_id="1", title="Eng", findings=findings)


# --- sibling_cli_dir ---


def test_sibling_cli_dir_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LJ_CLI_DIR", str(tmp_path))
    assert sibling_cli_dir() == tmp_path.resolve()


def test_sibling_cli_dir_defaults_to_sibling(monkeypatch, tmp_path):
    monkeypatch.delenv("LJ_CLI_DIR", raising=False)
    cwd_dir = tmp_path / "critics-cwd"
    cwd_dir.mkdir()
    sibling_repo = tmp_path / "linkedin-job-cli"
    sibling_repo.mkdir()
    monkeypatch.chdir(cwd_dir)

    assert sibling_cli_dir() == sibling_repo.resolve()


def test_sibling_cli_dir_raises_when_missing(monkeypatch, tmp_path):
    bogus = tmp_path / "does-not-exist"
    monkeypatch.setenv("LJ_CLI_DIR", str(bogus))

    with pytest.raises(FileNotFoundError) as excinfo:
        sibling_cli_dir()
    assert "LJ_CLI_DIR" in str(excinfo.value)


# --- build_handoff_prompt: round 1 (full) ---


def test_round1_prompt_includes_each_defect_field():
    report = _report(
        [_finding("salary", suggested_fix="internal/salary/parse.go:10"),
         _finding("location")]
    )
    prompt = build_handoff_prompt(report, round_num=1)

    assert "field: salary" in prompt
    assert "field: location" in prompt
    assert "<stored salary>" in prompt
    assert "<ev salary>" in prompt
    assert "internal/salary/parse.go:10" in prompt


def test_round1_prompt_omits_consistent_findings():
    report = _report(
        [_finding("salary"),
         _finding("company", consistent=True)]
    )
    prompt = build_handoff_prompt(report, round_num=1)

    assert "field: salary" in prompt
    assert "field: company" not in prompt


def test_round1_prompt_names_just_build():
    prompt = build_handoff_prompt(_report([_finding("salary")]), round_num=1)
    assert "just build" in prompt
    assert "Do not commit" in prompt


def test_round1_prompt_is_default():
    # round_num defaults to 1
    prompt = build_handoff_prompt(_report([_finding("salary")]))
    assert "field: salary" in prompt


# --- build_handoff_prompt: rounds 2+ (follow-up for resumed session) ---


def test_round2_prompt_names_still_failing_fields():
    report = _report([_finding("salary"), _finding("location")])
    prompt = build_handoff_prompt(report, round_num=2)

    assert "Round 2" in prompt
    assert "STILL inconsistent" in prompt
    assert "salary" in prompt
    assert "location" in prompt
    assert "<ev salary>" in prompt


def test_round2_prompt_omits_consistent_findings():
    report = _report([_finding("salary"), _finding("company", consistent=True)])
    prompt = build_handoff_prompt(report, round_num=2)

    assert "salary" in prompt
    assert "company" not in prompt


def test_round2_prompt_names_just_build():
    prompt = build_handoff_prompt(_report([_finding("salary")]), round_num=2)
    assert "just build" in prompt
    assert "try a different fix" in prompt


def test_round2_prompt_does_not_restate_job_intro():
    prompt = build_handoff_prompt(_report([_finding("salary")]), round_num=2)
    # the round-1 opener is absent — the resumed session already has it
    assert "You are fixing parsing defects" not in prompt


# --- launch_agent_session ---


class _FakeCompleted:
    returncode = 0


def test_launch_new_session_no_capture(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeCompleted()

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    rc = launch_agent_session("/fake/repo", "fix the parser")

    assert rc == 0
    assert captured["args"] == ["opencode", "/fake/repo", "--prompt", "fix the parser"]
    assert "capture_output" not in captured["kwargs"]
    assert "stdout" not in captured["kwargs"]


def test_launch_resume_session_includes_session_id(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return _FakeCompleted()

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    launch_agent_session("/fake/repo", "round 2 follow-up", session_id="ses_xyz")

    assert captured["args"] == [
        "opencode", "/fake/repo", "--session", "ses_xyz", "--prompt", "round 2 follow-up",
    ]


# --- latest_session_id ---


def test_latest_session_id_matches_directory(monkeypatch):
    sessions = [
        {"id": "ses_aaa", "directory": "/fake/repo"},
        {"id": "ses_bbb", "directory": "/other"},
    ]

    class FakeProc:
        returncode = 0
        stdout = json.dumps(sessions)

    monkeypatch.setattr(agent.subprocess, "run", lambda *a, **k: FakeProc())
    assert latest_session_id(__import__("pathlib").Path("/fake/repo")) == "ses_aaa"


def test_latest_session_id_none_when_no_match(monkeypatch):
    sessions = [{"id": "ses_bbb", "directory": "/other"}]

    class FakeProc:
        returncode = 0
        stdout = json.dumps(sessions)

    monkeypatch.setattr(agent.subprocess, "run", lambda *a, **k: FakeProc())
    from pathlib import Path
    assert latest_session_id(Path("/fake/repo")) is None


def test_latest_session_id_none_on_failure(monkeypatch):
    class FakeProc:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(agent.subprocess, "run", lambda *a, **k: FakeProc())
    from pathlib import Path
    assert latest_session_id(Path("/fake/repo")) is None
