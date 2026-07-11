"""Critics judge — compares each parsed field against the job description.

The judge has no tools; it uses ChatOpenAI.with_structured_output for
provider-enforced structured findings (more reliable than prompt-parsed JSON).
Falls back to a defensive JSON extractor for providers that don't honor
structured-output modes (notably some z.ai / glm-5.2 endpoints).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, ValidationError
from langchain_core.exceptions import OutputParserException
from langchain_openai import ChatOpenAI

try:  # optional: rich named spans in LangSmith when the `tracing` extra is installed
    from langsmith import traceable
except ImportError:  # pragma: no cover - langsmith is a transitive dep, fallback is a no-op
    def traceable(*dargs, **dkwargs):
        if callable(dargs[0]):
            return dargs[0]

        def _wrap(fn):
            return fn

        return _wrap

PARSED_FIELDS = ("salary", "location", "remote_type", "title", "company")

JUDGE_SYSTEM = (
    "You are a parsing-quality critic for a LinkedIn jobs CLI. For each parsed "
    "field, decide whether the stored value is consistent with the job's full "
    "description (the ground truth). Quote the description verbatim as evidence. "
    "When a field is inconsistent, name where the value should be sourced/fixed "
    "(e.g. salary often comes from the page's rounded card band while the real "
    "base salary is in the description body — point at the salary source). "
    "Assess every one of: salary, location, remote_type, title, company. "
    "Respond in JSON."
)

JSON_FALLBACK_INSTRUCTION = (
    "Respond with ONLY a single JSON object matching the CritiqueReport schema: "
    '{"job_id": str, "title": str, "findings": [{"field": str, '
    '"stored_value": str, "evidence_quote": str, "is_consistent": bool, '
    '"suggested_fix": str|null}]}. No markdown, no code fences, no prose.'
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


def _extract_json(text: str) -> str | None:
    """Pull the first JSON object out of a possibly-markdown-wrapped response."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return None


def header_tag_finding(job: dict, header_tags: dict | None) -> Finding | None:
    """Build a Finding when the stored remote_type disagrees with LinkedIn's
    authoritative workplace-type badge (the "header tag" from the Voyager
    jobPostings API).

    Returns None when the check is inconclusive — no header-tag data, the API
    soft-missed (no source), or LinkedIn returned no workplace signal — or when
    the stored value agrees with the badge. Only real mismatches surface, so
    the report stays focused on actionable defects.
    """
    if not header_tags or header_tags.get("source") != "voyager_api":
        return None
    live = (header_tags.get("remote_type") or "").strip().lower()
    if not live:
        return None
    stored = (job.get("remote_type") or "").strip().lower()
    if stored == live:
        return None
    urns = header_tags.get("workplace_type_urns") or []
    return Finding(
        field="remote_type (header tag)",
        stored_value=job.get("remote_type") or "(none)",
        evidence_quote=(
            f"LinkedIn Voyager jobPostings API: workplace_type_urns={urns}, "
            f"work_remote_allowed={header_tags.get('work_remote_allowed')}, "
            f"remote_type='{live}'."
        ),
        is_consistent=False,
        suggested_fix=(
            "Parser's DetectRemote heuristic overrode the authoritative "
            "workplaceTypes badge; prefer fetchJobPostingViaAPI's workplace "
            "type when the Voyager call succeeds. See internal/linkedin/"
            "scraper.go (DetectRemote at ingest + the API-fallback guard)."
        ),
    )


@traceable(name="judge_job")
def judge_job(job: dict, llm: ChatOpenAI) -> CritiqueReport:
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": _job_payload(job)},
    ]
    try:
        structured = llm.with_structured_output(CritiqueReport, method="json_mode")
        report = structured.invoke(messages)
    except (OutputParserException, ValidationError, ValueError) as e:
        raw = llm.invoke(
            messages + [{"role": "system", "content": JSON_FALLBACK_INSTRUCTION}]
        ).content
        extracted = _extract_json(raw)
        if not extracted:
            raise RuntimeError(
                f"judge returned no JSON; head={raw[:300]!r}"
            ) from e
        report = CritiqueReport.model_validate_json(extracted)

    report.job_id = str(job.get("id", report.job_id))
    if not getattr(report, "title", ""):
        report.title = job.get("title", "")
    return report
