from critics.judge import CritiqueReport, Finding, _fmt_salary, _job_payload


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
