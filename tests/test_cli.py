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
        self.captured_session_ids: list = []
        self.written_reports: list[list] = []
        self.next_session_id = "ses_test123"


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

    def fake_launch(path, prompt, session_id=None):
        state.launch_calls += 1
        state.captured_prompts.append(prompt)
        state.captured_session_ids.append(session_id)
        return 0

    def fake_latest_session_id(path):
        return state.next_session_id

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
    monkeypatch.setattr(cli, "header_tag_finding", lambda job, ht: None)
    monkeypatch.setattr(cli, "header_tags", lambda jid: None)
    monkeypatch.setattr(cli, "write_report", fake_write_report)
    monkeypatch.setattr(cli, "score_job", fake_score_job)
    monkeypatch.setattr(cli, "sibling_cli_dir", lambda: pathlib.Path("/fake/repo"))
    monkeypatch.setattr(cli, "launch_agent_session", fake_launch)
    monkeypatch.setattr(cli, "latest_session_id", fake_latest_session_id)
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


def test_ctrl_c_during_session_stops_gracefully(monkeypatch, loop):
    loop.judge_reports = [_report([_finding("salary")])]
    loop.inputs = ["y"]

    def raise_kb(path, prompt, session_id=None):
        loop.launch_calls += 1
        raise KeyboardInterrupt
    monkeypatch.setattr(cli, "launch_agent_session", raise_kb)

    rc = run_cli(loop)

    assert rc == 1
    assert loop.launch_calls == 1
    assert loop.score_calls == 0  # no re-score after interruption


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


# --- round 2 resumes the same opencode session with a follow-up (R8) ---


def test_round2_resumes_session_with_followup(loop):
    loop.judge_reports = [
        _report([_finding("salary")]),
        _report([_finding("salary")]),  # round-1 re-judge: still defective
        _report([_finding("salary", consistent=True)]),  # round-2 re-judge: clean
    ]
    loop.inputs = ["y", "y"]

    rc = run_cli(loop)

    assert rc == 0
    assert len(loop.captured_prompts) == 2
    # round 1: new session (session_id=None), full prompt
    assert loop.captured_session_ids[0] is None
    assert "You are fixing parsing defects" in loop.captured_prompts[0]
    # round 2: resumes the captured session id, concise follow-up prompt
    assert loop.captured_session_ids[1] == "ses_test123"
    assert "Round 2" in loop.captured_prompts[1]
    assert "STILL inconsistent" in loop.captured_prompts[1]
    assert "You are fixing parsing defects" not in loop.captured_prompts[1]


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


# --- header-tag check merges into the report even when the LLM judge is clean ---


def test_header_tag_mismatch_surfaces_when_judge_finds_nothing(monkeypatch, loop):
    """The motivating case: the LLM judge finds the stored fields consistent
    with the description, but LinkedIn's authoritative workplace badge disagrees
    with the stored remote_type. The header-tag finding must still surface so
    the loop prompts the user to fix the parser."""
    loop.judge_reports = [_report([_finding("salary", consistent=True)])]
    loop.inputs = ["n"]  # decline agent; we only care that the defect is reported

    ht_finding = Finding(
        field="remote_type (header tag)",
        stored_value="hybrid",
        evidence_quote="LinkedIn Voyager API: remote_type='remote'",
        is_consistent=False,
        suggested_fix="scraper.go",
    )
    monkeypatch.setattr(cli, "header_tag_finding", lambda job, ht: ht_finding)
    monkeypatch.setattr(cli, "header_tags", lambda jid: {"source": "voyager_api", "remote_type": "remote"})

    rc = run_cli(loop)

    # The header-tag finding was merged into the report, so defects are non-empty
    # and the user is prompted (rather than the "nothing to fix" short-circuit).
    assert rc == 0
    assert loop.input_calls == 1
    written = loop.written_reports[0][0]
    assert any(
        f.field == "remote_type (header tag)" and not f.is_consistent for f in written.findings
    )


def test_header_tag_unavailable_does_not_block(monkeypatch, loop):
    """When header-tags can't run (no session / CLI error), the judge-only
    flow proceeds normally without surfacing a header-tag finding."""
    loop.judge_reports = [_report([_finding("salary", consistent=True)])]
    loop.inputs = []
    monkeypatch.setattr(cli, "header_tags", lambda jid: None)
    monkeypatch.setattr(cli, "header_tag_finding", lambda job, ht: None)

    rc = run_cli(loop)

    assert rc == 0
    assert loop.input_calls == 0
    written = loop.written_reports[0][0]
    assert all(f.field != "remote_type (header tag)" for f in written.findings)
