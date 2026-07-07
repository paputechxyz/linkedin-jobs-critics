import pathlib

import pytest

from critics import cli
from critics.judge import CritiqueReport, Finding


def _finding(field, consistent=False):
    return Finding(
        field=field,
        stored_value=f"<{field}>",
        evidence_quote=f"<ev {field}>",
        is_consistent=consistent,
        suggested_fix=None,
    )


def _report(findings):
    return CritiqueReport(job_id="1", title="Eng", findings=findings)


class Loop:
    """Mutable state + call recorder for the cli loop tests."""

    def __init__(self):
        self.judge_reports: list[CritiqueReport] = []
        self.inputs: list[str] = []
        self.version_before = "0.1.0"
        self.version_after = "0.1.1"

        self.judge_calls = 0
        self.write_calls = 0
        self.score_calls = 0
        self.launch_calls = 0
        self.version_calls = 0
        self.input_calls = 0

        self.captured_prompts: list[str] = []
        self.written_reports: list[list] = []


@pytest.fixture
def loop(monkeypatch, tmp_path):
    state = Loop()
    state.out_path = str(tmp_path / "plan.md")

    def fake_judge_job(job, llm):
        state.judge_calls += 1
        return state.judge_reports.pop(0)

    def fake_write_report(reports, out):
        state.write_calls += 1
        state.written_reports.append(list(reports))
        return pathlib.Path(out)

    def fake_score_job(jid):
        state.score_calls += 1
        return {"id": jid, "title": "Eng", "description": "d"}

    def fake_launch(path, prompt):
        state.launch_calls += 1
        state.captured_prompts.append(prompt)
        return 0

    def fake_cli_version():
        state.version_calls += 1
        # odd call in a round = before, even = after
        return state.version_before if state.version_calls % 2 == 1 else state.version_after

    def fake_input(_prompt=""):
        state.input_calls += 1
        return state.inputs.pop(0)

    monkeypatch.setattr(cli, "load_llm", lambda: "fake-llm")
    monkeypatch.setattr(cli, "show_job", lambda jid: {"id": jid, "title": "Eng", "description": "d"})
    monkeypatch.setattr(cli, "judge_job", fake_judge_job)
    monkeypatch.setattr(cli, "write_report", fake_write_report)
    monkeypatch.setattr(cli, "score_job", fake_score_job)
    monkeypatch.setattr(cli, "sibling_cli_dir", lambda: pathlib.Path("/fake/repo"))
    monkeypatch.setattr(cli, "launch_agent_session", fake_launch)
    monkeypatch.setattr(cli, "cli_version", fake_cli_version)
    monkeypatch.setattr("builtins.input", fake_input)

    return state


def run_cli(state, job_id="1"):
    return cli.main([job_id, "-o", state.out_path])


# --- gating (R1, R2, R14) ---


def test_no_defects_skips_prompt_and_exits(loop):
    loop.judge_reports = [_report([_finding("salary", consistent=True)])]
    loop.inputs = []  # input must not be called

    rc = run_cli(loop)

    assert rc == 0
    assert loop.input_calls == 0
    assert loop.launch_calls == 0
    assert loop.version_calls == 0


def test_user_declines_no_agent_spawned(loop):
    loop.judge_reports = [_report([_finding("salary")])]
    loop.inputs = ["n"]

    rc = run_cli(loop)

    assert rc == 0
    assert loop.launch_calls == 0
    assert loop.score_calls == 0
    assert loop.version_calls == 0


def test_user_empty_answer_means_no(loop):
    loop.judge_reports = [_report([_finding("salary")])]
    loop.inputs = [""]

    rc = run_cli(loop)

    assert rc == 0
    assert loop.launch_calls == 0


# --- version check (R15, AE4) ---


def test_version_unchanged_after_session_stops(loop):
    loop.judge_reports = [_report([_finding("salary")])]
    loop.inputs = ["y"]
    loop.version_before = "0.1.0"
    loop.version_after = "0.1.0"

    rc = run_cli(loop)

    assert rc == 1
    assert loop.launch_calls == 1
    assert loop.score_calls == 0  # re-score skipped
    assert loop.judge_calls == 1  # no re-judge


def test_version_dev_after_session_stops(loop):
    loop.judge_reports = [_report([_finding("salary")])]
    loop.inputs = ["y"]
    loop.version_before = "0.1.0"
    loop.version_after = "dev"

    rc = run_cli(loop)

    assert rc == 1
    assert loop.launch_calls == 1
    assert loop.score_calls == 0


def test_version_bumped_proceeds_to_rescore(loop):
    loop.judge_reports = [
        _report([_finding("salary")]),
        _report([_finding("salary", consistent=True)]),
    ]
    loop.inputs = ["y"]
    loop.version_before = "0.1.0"
    loop.version_after = "0.1.1"

    rc = run_cli(loop)

    assert rc == 0
    assert loop.version_calls == 2  # before + after
    assert loop.score_calls == 1
    assert loop.judge_calls == 2


# --- convergence & repeat (R9, R10, R11) ---


def test_clean_rejudge_exits_with_success(loop):
    loop.judge_reports = [
        _report([_finding("salary")]),
        _report([_finding("salary", consistent=True)]),
    ]
    loop.inputs = ["y"]

    rc = run_cli(loop)

    assert rc == 0
    assert loop.write_calls == 2  # initial + post-re-judge
    assert loop.launch_calls == 1


def test_defective_rejudge_then_decline(loop):
    loop.judge_reports = [
        _report([_finding("salary")]),
        _report([_finding("salary")]),  # still defective after round 1
    ]
    loop.inputs = ["y", "n"]

    rc = run_cli(loop)

    assert rc == 0
    assert loop.write_calls == 2
    assert loop.launch_calls == 1
    assert loop.judge_calls == 2


# --- round context (R8) ---


def test_round2_prompt_includes_prior_history(loop):
    loop.judge_reports = [
        _report([_finding("salary")]),
        _report([_finding("salary")]),  # round-1 re-judge: still defective
        _report([_finding("salary", consistent=True)]),  # round-2 re-judge: clean
    ]
    loop.inputs = ["y", "y"]

    rc = run_cli(loop)

    assert rc == 0
    assert len(loop.captured_prompts) == 2
    assert "Prior rounds" not in loop.captured_prompts[0]
    assert "Prior rounds" in loop.captured_prompts[1]
    assert "round 1" in loop.captured_prompts[1]
    assert "salary" in loop.captured_prompts[1]


# --- full re-judge surfaces regressions (R12, AE3) ---


def test_regression_new_defect_in_round2_plan(loop):
    loop.judge_reports = [
        _report([_finding("salary")]),
        _report([_finding("location")]),  # salary fixed, location regressed
    ]
    loop.inputs = ["y", "n"]

    rc = run_cli(loop)

    assert rc == 0
    assert loop.write_calls == 2
    round2_report = loop.written_reports[1][0]
    assert any(f.field == "location" and not f.is_consistent for f in round2_report.findings)
