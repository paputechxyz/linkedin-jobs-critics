from critics.judge import CritiqueReport, Finding
from critics.report import write_report


def _report(job_id, title, findings):
    return CritiqueReport(job_id=job_id, title=title, findings=findings)


def test_renders_inconsistent_finding(tmp_path):
    f = Finding(
        field="salary",
        stored_value="CAD$100,000 - $180,000",
        evidence_quote="Base salary range: $147,996 - $185,004",
        is_consistent=False,
        suggested_fix="salary source: internal/linkedin/scraper.go:108",
    )
    out = write_report([_report("999", "Senior Software Engineer", [f])], str(tmp_path / "plan.md"))

    text = out.read_text()
    assert "Senior Software Engineer" in text
    assert "`999`" in text
    assert "CAD$100,000 - $180,000" in text
    assert "Base salary range" in text
    assert "scraper.go:108" in text
    assert "1 parsing defect" in text


def test_no_issues_when_all_consistent(tmp_path):
    r = _report(
        "1",
        "Eng",
        [Finding(field="title", stored_value="Eng", evidence_quote="Eng", is_consistent=True)],
    )
    out = write_report([r], str(tmp_path / "plan.md"))

    assert "No issues found" in out.read_text()


def test_includes_evidence_and_fix_only_when_inconsistent(tmp_path):
    ok = Finding(field="company", stored_value="Acme", evidence_quote="Acme", is_consistent=True)
    bad = Finding(
        field="salary",
        stored_value="x",
        evidence_quote="the quote",
        is_consistent=False,
        suggested_fix="fix target",
    )
    out = write_report([_report("1", "T", [ok, bad])], str(tmp_path / "p.md"))

    text = out.read_text()
    assert "fix target" in text
    assert "the quote" in text
