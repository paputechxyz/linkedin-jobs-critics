import json

import pytest

from critics import tools


class FakeProc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_fetch_jobs_parses(monkeypatch):
    jobs = [{"id": "1", "title": "Eng"}, {"id": "2", "title": "Sr Eng"}]
    monkeypatch.setattr(tools, "_run", lambda args, timeout=60: FakeProc(stdout=json.dumps(jobs)))
    assert tools.fetch_jobs() == jobs


def test_fetch_jobs_raises_on_error(monkeypatch):
    monkeypatch.setattr(tools, "_run", lambda args, timeout=60: FakeProc(stderr="nope", returncode=1))
    with pytest.raises(RuntimeError):
        tools.fetch_jobs()


def test_search_tool_returns_compact_summary(monkeypatch):
    jobs = [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    monkeypatch.setattr(tools, "_run", lambda args, timeout=180: FakeProc(stdout=json.dumps(jobs)))

    out = tools.linkedin_jobs_search.invoke({"keywords": "Eng", "location": "Toronto"})

    data = json.loads(out)
    assert data["count"] == 3
    assert data["ids"] == ["1", "2", "3"]


def test_search_tool_surfaces_cli_error(monkeypatch):
    monkeypatch.setattr(tools, "_run", lambda args, timeout=180: FakeProc(stderr="boom", returncode=2))

    out = tools.linkedin_jobs_search.invoke({"keywords": "Eng", "location": "Toronto"})

    assert out.startswith("ERROR (exit 2)")


def test_search_tool_uses_force_overwrite_flag(monkeypatch):
    captured = {}

    def fake_run(args, timeout=180):
        captured["args"] = args
        return FakeProc(stdout="[]")

    monkeypatch.setattr(tools, "_run", fake_run)
    tools.linkedin_jobs_search.invoke({"keywords": "Eng", "location": "Toronto"})

    assert "--force-overwrite" in captured["args"]
    assert "--json" in captured["args"]
