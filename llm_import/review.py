"""Strukturierte Review-Entscheidungen für den LLM-Importer."""

from dataclasses import dataclass, field as dataclass_field


@dataclass
class ReviewFinding:
    code: str
    severity: str
    field: str | None = None
    message: str = ""
    details: dict = dataclass_field(default_factory=dict)


@dataclass
class ReviewReport:
    findings: list[ReviewFinding] = dataclass_field(
        default_factory=list
    )

    def add(
        self,
        code,
        severity,
        field_name=None,
        message="",
        details=None,
    ):
        if severity not in {"info", "warning", "error"}:
            raise ValueError(
                f"Ungültiger Schweregrad: {severity}"
            )

        self.findings.append(
            ReviewFinding(
                code=code,
                severity=severity,
                field=field_name,
                message=message,
                details=details or {},
            )
        )

    @property
    def requires_review(self):
        return any(
            item.severity in {"warning", "error"}
            for item in self.findings
        )

    @property
    def status(self):
        return (
            "REVIEW"
            if self.requires_review
            else "VALIDATED"
        )

    def print_report(self):
        print("\n===== STRUKTURIERTER PRÜFBERICHT =====")
        print(f"STATUS: {self.status}")

        for item in self.findings:
            name = f" ({item.field})" if item.field else ""

            print(
                f"[{item.severity.upper()}] "
                f"{item.code}{name}: {item.message}"
            )
            
def add_legacy_issues(report, issues, source_findings):
    """Überführt bisherige Prüfmeldungen ohne Informationsverlust."""

    # Quellenkonflikte wurden bereits strukturiert übernommen.
    # Ihre alten Textmeldungen nicht ein zweites Mal aufnehmen.
    source_messages = {
        f"{finding['code']}: "
        f"{finding.get('field', 'document')} – {finding}"
        for finding in source_findings
    }

    for issue in issues:
        message = str(issue)

        if message in source_messages:
            continue

        if message.startswith("LLM:"):
            code = "LLM_WARNING_UNVERIFIED"
        else:
            code = "VALIDATION_ISSUE_UNRESOLVED"

        report.add(
            code=code,
            severity="warning",
            message=message,
        )