"""Improvement-plan markdown writer."""

from __future__ import annotations

from pathlib import Path

from .judge import CritiqueReport


def write_report(reports: list[CritiqueReport], out_path: str) -> Path:
    inconsistent: list[tuple[CritiqueReport, object]] = []
    consistent_count = 0
    for r in reports:
        for f in r.findings:
            if f.is_consistent:
                consistent_count += 1
            else:
                inconsistent.append((r, f))

    lines = ["# Critics - Improvement Plan", ""]
    if not inconsistent:
        lines.append(
            f"No issues found across {len(reports)} job(s) "
            f"({consistent_count} field(s) checked)."
        )
        lines.append("")
        path = Path(out_path)
        path.write_text("\n".join(lines))
        return path

    buggy_jobs = {r.job_id for r, _ in inconsistent}
    lines.append(
        f"{len(inconsistent)} parsing defect(s) across {len(buggy_jobs)} job(s). "
        f"{consistent_count} field(s) were consistent."
    )
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    for r, f in inconsistent:
        lines.append(f"### {r.title} (`{r.job_id}`) - {f.field}")
        lines.append("")
        lines.append(f"- **Stored value:** {f.stored_value}")
        lines.append(f"- **Evidence (from description):** > {f.evidence_quote}")
        if f.suggested_fix:
            lines.append(f"- **Suggested fix:** {f.suggested_fix}")
        lines.append("")

    path = Path(out_path)
    path.write_text("\n".join(lines))
    return path
