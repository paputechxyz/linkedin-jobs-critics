import subprocess

import pytest

from critics import agent
from critics.agent import (
    build_handoff_prompt,
    launch_agent_session,
    sibling_cli_dir,
)
from critics.judge import CritiqueReport, Finding


def _report(findings):
    return CritiqueReport(job_id="4259504707", title="Eng", findings=findings)


def _defect(field="salary", suggested_fix=None):
    return Finding(
        field=field,
        stored_value=f"<stored {field}>",
        evidence_quote=f"<evidence {field}>",
        is_consistent=False,
        suggested_fix=suggested_fix,
    )


# --- sibling_cli_dir ---


def test_sibling_cli_dir_honors_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LJ_CLI_DIR", str(tmp_path))
    assert sibling_cli_dir() == tmp_path.resolve()


def test_sibling_cli_dir_defaults_to_sibling(monkeypatch, tmp_path):
    monkeypatch.delenv("LJ_CLI_DIR", raising=False)
    # default resolves `<cwd>/../linkedin-job-cli` — i.e. a sibling of cwd.
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


# --- build_handoff_prompt ---


def test_build_handoff_prompt_includes_each_defect_field():
    report = _report(
        [_defect("salary", suggested_fix="salary source: internal/salary/parse.go:10"),
         _defect("location")]
    )
    prompt = build_handoff_prompt(report)

    assert "field: salary" in prompt
    assert "field: location" in prompt
    assert "<stored salary>" in prompt
    assert "<evidence salary>" in prompt
    assert "internal/salary/parse.go:10" in prompt
    assert "<stored location>" in prompt


def test_build_handoff_prompt_omits_consistent_findings():
    report = _report(
        [_defect("salary"),
         Finding(field="company", stored_value="x", evidence_quote="y",
                 is_consistent=True, suggested_fix=None)]
    )
    prompt = build_handoff_prompt(report)

    assert "field: salary" in prompt
    assert "field: company" not in prompt


def test_build_handoff_prompt_always_names_just_build():
    report = _report([_defect("salary")])
    prompt = build_handoff_prompt(report)

    assert "just build" in prompt
    assert "NOT plain `go build`" in prompt
    assert "Do not commit" in prompt


def test_build_handoff_prompt_omits_history_block_when_empty():
    report = _report([_defect("salary")])
    prompt = build_handoff_prompt(report)

    assert "Prior rounds" not in prompt


def test_build_handoff_prompt_includes_history_block_when_non_empty():
    report = _report([_defect("salary")])
    history = [
        {"round": 1, "fields_attempted": ["salary"], "fields_still_failing": ["salary"]},
    ]
    prompt = build_handoff_prompt(report, history=history)

    assert "Prior rounds" in prompt
    assert "round 1" in prompt
    assert "salary" in prompt


# --- launch_agent_session ---


def test_launch_agent_session_invokes_opencode_without_capture(monkeypatch):
    captured = {}

    class FakeCompleted:
        returncode = 0

    def fake_run(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return FakeCompleted()

    monkeypatch.setattr(agent.subprocess, "run", fake_run)
    rc = launch_agent_session("/path/to/repo", "fix the parser")

    assert rc == 0
    assert captured["args"] == ["opencode", "/path/to/repo", "--prompt", "fix the parser"]
    assert "capture_output" not in captured["kwargs"]
    assert "stdout" not in captured["kwargs"]
