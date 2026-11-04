"""Read-only audit of numbered PDF heading candidates.

Reports structural plausibility, NOT verified headings. Only manually checked
anchors should be sent to extract_verified_section_chunks.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from scripts.pdf_heading_candidates import HeadingCandidate

_NUMBER = re.compile(r"^([1-9][0-9]?(?:\.[0-9]+){0,3})\s+")


@dataclass(frozen=True)
class HeadingAudit:
    candidate: HeadingCandidate
    number: str
    status: str
    reason: str


def audit_candidates(candidates: list[HeadingCandidate]) -> list[HeadingAudit]:
    """Flag missing/wrong parent, ordering and numeric anomalies.

    Does not assign confidence scores or automatically approve headings.
    """
    results: list[HeadingAudit] = []
    seen: set[str] = set()
    current_main: str | None = None
    previous: dict[str, int] = {}
    for item in candidates:
        match = _NUMBER.match(item.heading)
        if not match:
            results.append(HeadingAudit(item, "", "REVIEW", "No section number"))
            continue
        number = match.group(1)
        parts = number.split(".")
        major = parts[0]
        reasons: list[str] = []
        if number in seen:
            reasons.append("Repeated section number")
        seen.add(number)

        if len(parts) == 1:
            current_main = major
        else:
            if current_main != major:
                reasons.append(f"Outside current main chapter {current_main or 'none'}")
            parent = ".".join(parts[:-1])
            # Missing parents are warnings, not proof of wrong data:
            # scanning only the first 14 lines can miss real headings.
            if parent not in seen:
                reasons.append(f"Parent {parent} not detected")
            subsection_index = int(parts[-1])
            last = previous.get(parent)
            if last is not None and subsection_index <= last:
                reasons.append("Non-increasing subsection number")
            previous[parent] = subsection_index
        results.append(HeadingAudit(
            candidate=item,
            number=number,
            status="REVIEW" if reasons else "CANDIDATE",
            reason="; ".join(reasons) if reasons else "No structural anomaly detected",
        ))
    return results


def format_report(results: list[HeadingAudit]) -> str:
    """Tab-separated review text, suitable for redirecting to a local .tsv."""
    lines = ["pdf_page\tlevel\tsection\tstatus\treason\theading"]
    for row in results:
        clean = lambda value: str(value).replace("\t", " ").replace("\n", " ")
        lines.append("\t".join(map(clean, (
            row.candidate.pdf_page, row.candidate.level, row.number,
            row.status, row.reason, row.candidate.heading
        ))))
    return "\n".join(lines) + "\n"
