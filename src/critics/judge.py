"""Critics judge — compares each parsed field against the job description.

The judge has no tools; it uses ChatOpenAI.with_structured_output for
provider-enforced structured findings (more reliable than prompt-parsed JSON).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

PARSED_FIELDS = ("salary", "location", "remote_type", "title", "company")

JUDGE_SYSTEM = (
    "You are a parsing-quality critic for a LinkedIn jobs CLI. For each parsed "
    "field, decide whether the stored value is consistent with the job's full "
    "description (the ground truth). Quote the description verbatim as evidence. "
    "When a field is inconsistent, name where the value should be sourced/fixed "
    "(e.g. salary often comes from the page's rounded card band while the real "
    "base salary is in the description body — point at the salary source). "
    "Assess every one of: salary, location, remote_type, title, company."
)


class Finding(BaseModel):
    field: str = Field(
        description="The parsed field under review: one of salary, location, remote_type, title, company."
    )
    stored_value: str = Field(description="The value currently stored for this field.")
    evidence_quote: str = Field(
        description="A verbatim quote from the job description supporting the assessment."
    )
    is_consistent: bool = Field(
        description="True if the stored value agrees with the description."
    )
    suggested_fix: str | None = Field(
        None,
        description="When inconsistent, the source location of the parsed value to fix, "
        "e.g. 'salary source: internal/linkedin/scraper.go:108'.",
    )


class CritiqueReport(BaseModel):
    job_id: str
    title: str
    findings: list[Finding]


def _fmt_salary(job: dict) -> str:
    raw = job.get("salary_raw")
    if raw:
        return raw
    lo, hi = job.get("salary_low"), job.get("salary_high")
    cur = job.get("salary_currency") or "USD"
    if lo is not None and hi is not None:
        return f"{cur}${lo} - ${hi}"
    if hi is not None:
        return f"{cur}${hi}"
    if lo is not None:
        return f"{cur}${lo}"
    return "N/A"


def _job_payload(job: dict) -> str:
    return (
        f"Job ID: {job.get('id', '')}\n"
        f"Title (stored): {job.get('title', '')}\n"
        f"Company (stored): {job.get('company', '')}\n"
        f"Location (stored): {job.get('location', '')}\n"
        f"Remote type (stored): {job.get('remote_type', '') or '(none)'}\n"
        f"Salary (stored): {_fmt_salary(job)}\n\n"
        f"Full description (ground truth):\n{job.get('description', '') or '(empty)'}"
    )


def judge_job(job: dict, llm: ChatOpenAI) -> CritiqueReport:
    structured = llm.with_structured_output(CritiqueReport, method="json_schema")
    report = structured.invoke(
        [
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": _job_payload(job)},
        ]
    )
    report.job_id = str(job.get("id", report.job_id))
    if not getattr(report, "title", ""):
        report.title = job.get("title", "")
    return report
