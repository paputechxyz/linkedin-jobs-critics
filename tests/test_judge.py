from critics.judge import (
    CritiqueReport,
    Finding,
    _extract_json,
    _fmt_salary,
    _job_payload,
    judge_job,
)


def test_fmt_salary_range():
    assert (
        _fmt_salary({"salary_low": 100000, "salary_high": 180000, "salary_currency": "CAD"})
        == "CAD$100000 - $180000"
    )


def test_fmt_salary_prefers_raw():
    assert _fmt_salary({"salary_raw": "CA$100k", "salary_low": 1, "salary_high": 2}) == "CA$100k"


def test_fmt_salary_none():
    assert _fmt_salary({}) == "N/A"


def test_job_payload_includes_all_fields():
    payload = _job_payload(
        {
            "id": "9",
            "title": "Eng",
            "company": "Acme",
            "location": "Toronto",
            "remote_type": "remote",
            "description": "We build things.",
        }
    )
    for needle in ("Eng", "Acme", "Toronto", "remote", "We build things."):
        assert needle in payload


def test_finding_model_roundtrip():
    f = Finding(
        field="salary",
        stored_value="CAD$100,000 - $180,000",
        evidence_quote="Base salary range: $147,996 - $185,004",
        is_consistent=False,
        suggested_fix="salary source: internal/linkedin/scraper.go:108",
    )
    assert f.is_consistent is False
    assert f.suggested_fix.endswith("scraper.go:108")


def test_critique_report_model():
    r = CritiqueReport(
        job_id="999",
        title="Senior Software Engineer",
        findings=[Finding(field="title", stored_value="x", evidence_quote="y", is_consistent=True)],
    )
    assert r.job_id == "999"
    assert len(r.findings) == 1


def test_extract_json_fenced_block():
    raw = 'Here you go:\n```json\n{"job_id": "1", "title": "x", "findings": []}\n```\n'
    assert _extract_json(raw) == '{"job_id": "1", "title": "x", "findings": []}'


def test_extract_json_bare_blob():
    raw = 'Prose prose {"job_id": "1", "title": "x", "findings": []} trailing'
    assert _extract_json(raw) == '{"job_id": "1", "title": "x", "findings": []}'


def test_extract_json_returns_none_when_absent():
    assert _extract_json("no json anywhere here") is None


class _FakeLLM:
    """Mimics ChatOpenAI enough for judge_job: a structured-output path that
    can be made to fail, and a raw .invoke() that returns a string .content."""

    def __init__(self, structured_exc: Exception, raw_content: str):
        self._structured_exc = structured_exc
        self._raw_content = raw_content
        self.invoked: list = []

    def with_structured_output(self, schema, method=None):
        def _invoke(messages):
            self.invoked.append(("structured", messages))
            raise self._structured_exc

        return type("S", (), {"invoke": staticmethod(_invoke)})()

    def invoke(self, messages):
        self.invoked.append(("raw", messages))
        return type("R", (), {"content": self._raw_content})()


def test_judge_job_falls_back_when_structured_output_fails():
    raw = (
        'Here is the report:\n```json\n'
        '{"job_id": "1", "title": "Eng", "findings": ['
        '{"field": "salary", "stored_value": "x", "evidence_quote": "q", '
        '"is_consistent": false, "suggested_fix": null}'
        "]}```"
    )
    llm = _FakeLLM(structured_exc=ValueError("provider ignored json_mode"), raw_content=raw)

    report = judge_job({"id": "1", "title": "Eng", "description": "q"}, llm)

    assert isinstance(report, CritiqueReport)
    assert report.job_id == "1"
    assert report.findings[0].field == "salary"
    # both paths were attempted
    assert [kind for kind, _ in llm.invoked] == ["structured", "raw"]


def test_judge_job_raises_when_fallback_returns_no_json():
    llm = _FakeLLM(structured_exc=ValueError("boom"), raw_content="just prose, no json")
    try:
        judge_job({"id": "1", "title": "Eng", "description": "x"}, llm)
    except RuntimeError as e:
        assert "no JSON" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
