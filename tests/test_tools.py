import json

import pytest

from critics import tools


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_show_job_returns_dict(monkeypatch):
    job = {"id": "4259504707", "title": "Eng"}
    monkeypatch.setattr(tools, "_run", lambda args, timeout=60: FakeProc(stdout=json.dumps(job)))

    assert tools.show_job("4259504707") == job


def test_show_job_passes_id_and_json_flags(monkeypatch):
    captured = {}

    def fake_run(args, timeout=60):
        captured["args"] = args
        return FakeProc(stdout=json.dumps({"id": "1"}))

    monkeypatch.setattr(tools, "_run", fake_run)
    tools.show_job("4259504707")

    assert captured["args"] == ["show", "4259504707", "--json"]


def test_show_job_returns_none_when_not_stored(monkeypatch):
    # non-zero exit, no stdout -> treated as "not in DB"
    monkeypatch.setattr(
        tools, "_run", lambda args, timeout=60: FakeProc(stderr="not found", returncode=1)
    )
    assert tools.show_job("999") is None


def test_show_job_returns_none_on_empty_stdout(monkeypatch):
    monkeypatch.setattr(tools, "_run", lambda args, timeout=60: FakeProc(stdout=""))
    assert tools.show_job("999") is None


def test_show_job_returns_none_on_non_json(monkeypatch):
    monkeypatch.setattr(tools, "_run", lambda args, timeout=60: FakeProc(stdout="not json"))
    assert tools.show_job("999") is None


def test_show_job_unwraps_single_element_list(monkeypatch):
    job = {"id": "1", "title": "Eng"}
    monkeypatch.setattr(tools, "_run", lambda args, timeout=60: FakeProc(stdout=json.dumps([job])))
    assert tools.show_job("1") == job


def test_score_job_returns_dict(monkeypatch):
    job = {"id": "4259504707", "title": "Eng"}
    monkeypatch.setattr(tools, "_run", lambda args, timeout=180: FakeProc(stdout=json.dumps(job)))

    assert tools.score_job("4259504707") == job


def test_score_job_passes_id_and_json_flags(monkeypatch):
    captured = {}

    def fake_run(args, timeout=180):
        captured["args"] = args
        return FakeProc(stdout=json.dumps({"id": "1"}))

    monkeypatch.setattr(tools, "_run", fake_run)
    tools.score_job("4259504707")

    assert captured["args"] == ["score-job", "4259504707", "--json"]


def test_score_job_raises_on_failure(monkeypatch):
    monkeypatch.setattr(
        tools,
        "_run",
        lambda args, timeout=180: FakeProc(stderr="boom", returncode=2),
    )
    with pytest.raises(RuntimeError) as excinfo:
        tools.score_job("4259504707")
    assert "exit 2" in str(excinfo.value)
    assert "4259504707" in str(excinfo.value)


def test_score_job_raises_on_non_json(monkeypatch):
    monkeypatch.setattr(tools, "_run", lambda args, timeout=180: FakeProc(stdout="not json"))
    with pytest.raises(RuntimeError):
        tools.score_job("4259504707")
