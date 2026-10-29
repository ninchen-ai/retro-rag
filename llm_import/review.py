"""Strukturierte Review-Entscheidungen für den LLM-Importer."""

from dataclasses import dataclass, field as dataclass_field
from llm_import.validation import normalize_evidence, verify_value, verify_api_support_evidence, verify_gpu_field_evidence, GPU_SEMANTICALLY_VERIFIED_FIELDS, verify_api_support_evidence


@dataclass
class ReviewFinding:
    code: str
    severity: str
    field: str | None = None
    message: str = ""
    details: dict = dataclass_field(default_factory=dict)

@dataclass
class ValidationIssue:
    """Ein technischer Validierungsbefund vor der Normalisierung."""

    code: str
    field: str | None
    message: str
    resolved: bool = False

@dataclass
class ReviewReport:
    findings: list[ReviewFinding] = dataclass_field(
        default_factory=list
    )
    llm_diagnostics: list[str] = dataclass_field(
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

    def add_llm_diagnostic(self, message: str):
        """Speichert die ursprüngliche LLM-Diagnose getrennt."""
        if not isinstance(message, str):
            raise TypeError("LLM-Diagnose muss ein String sein")

        message = message.strip()

        if message and message not in self.llm_diagnostics:
            self.llm_diagnostics.append(message)

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
            report.add_llm_diagnostic(message)
        else:
            code = "VALIDATION_ISSUE_UNRESOLVED"

        report.add(
            code=code,
            severity="warning",
            message=message,
        )

def evaluate_final_fields(specs: dict, evidence: dict) -> ReviewReport:
    """Prüft die Konsistenz finaler Werte und Konfliktmarkierungen.

    Keine vollständige Freigabeentscheidung.
    """
    report = ReviewReport()

    if not isinstance(specs, dict) or not isinstance(evidence, dict):
        report.add(
            "INVALID_REVIEW_INPUT",
            "error",
            message="Spezifikationen oder Belege sind kein Objekt",
        )
        return report

    for field_name, value in specs.items():
        item = evidence.get(field_name)

        if not isinstance(item, dict):
            report.add(
                "EVIDENCE_MISSING",
                "error",
                field_name,
                "Belegstruktur fehlt oder ist ungültig",
            )
            continue

        origin = item.get("origin")

        if origin in {"conflict", "validation_conflict"}:
            report.add(
                code=(
                    "CONFLICTING_VALUES"
                    if origin == "conflict"
                    else "VALIDATION_CONFLICT"
                ),
                severity="error",
                field_name=field_name,
                message="Ungeklärter Widerspruch",
                details={
                    "candidates": item.get("candidates", []),
                },
            )

            if value is not None or item.get("value") is not None:
                report.add(
                    "CONFLICT_VALUE_NOT_BLOCKED",
                    "error",
                    field_name,
                    "Konfliktfeld enthält trotz Sperre einen Wert",
                )

            continue

        if item.get("value") != value:
            report.add(
                "EVIDENCE_VALUE_MISMATCH",
                "error",
                field_name,
                "Finaler Wert und Belegwert stimmen nicht überein",
                details={
                    "spec_value": value,
                    "evidence_value": item.get("value"),
                },
            )

    for field_name in evidence.keys() - specs.keys():
        report.add(
            "UNEXPECTED_EVIDENCE_FIELD",
            "error",
            field_name,
            "Beleg ohne zugehöriges Spezifikationsfeld",
        )

    return report

def separate_legacy_issues(issues: list[str]) -> tuple[list[str], list[str]]:
    """Trennt technische Validierungsprobleme von LLM-Diagnosen."""
    validation_problems = []
    llm_diagnostics = []

    for issue in issues:
        if not isinstance(issue, str):
            raise TypeError("Prüfmeldung muss ein String sein")

        if issue.startswith("LLM:"):
            llm_diagnostics.append(issue)
        else:
            validation_problems.append(issue)

    return validation_problems, llm_diagnostics

def evaluate_gpu_evidence(
    specs: dict,
    evidence: dict,
    source: str,
) -> ReviewReport:
    """Prüft alle nichtleeren finalen GPU-Felder gegen die Quelle."""

    report = ReviewReport()

    for field, value in specs.items():

        if value is None or value == []:
            continue

        if field not in GPU_SEMANTICALLY_VERIFIED_FIELDS:
            report.add(
                code="UNVERIFIED_FIELD",
                severity="error",
                field_name=field,
                message="Keine semantische Prüfroutine vorhanden",
            )
            continue

        item = evidence.get(field)

        if not isinstance(item, dict):
            report.add(
                code="FINAL_EVIDENCE_INVALID",
                severity="error",
                field_name=field,
                message="Belegstruktur fehlt",
            )
            continue

        if item.get("origin") in {
            "conflict",
            "validation_conflict",
            "rejected",
        }:
            report.add(
                code="FINAL_EVIDENCE_INVALID",
                severity="error",
                field_name=field,
                message="Feld besitzt keinen freigabefähigen Ursprung",
            )
            continue

        if item.get("value") != value:
            report.add(
                code="FINAL_EVIDENCE_INVALID",
                severity="error",
                field_name=field,
                message="Wert und Belegwert stimmen nicht überein",
            )
            continue

        if field == "api_support":
            valid = verify_api_support_evidence(
                value,
                item.get("evidence"),
                source,
            )
        else:
            valid = verify_gpu_field_evidence(
                field,
                value,
                item.get("evidence"),
                source,
            )

        if not valid:
            report.add(
                code="FINAL_EVIDENCE_INVALID",
                severity="error",
                field_name=field,
                message="Finaler Wert wird durch den Quellenbeleg nicht bestätigt",
            )

    return report

def evaluate_final_review(
    validation_issues: list[ValidationIssue],
    source_findings: list[dict],
    specs: dict,
    evidence: dict,
    source: str,
) -> ReviewReport:
    """Führt technische Prüfungen konservativ zusammen."""

    report = ReviewReport()

    validation_issues = resolve_validation_issues(
        validation_issues,
        specs,
        evidence,
        source,
    )

    # 1. Strukturierte Validierungsfehler
    for issue in validation_issues:
        if issue.code == "NO_VERIFIED_SPECS":
            has_verified_specs = any(
                type(value) is int
                and isinstance(evidence.get(field_name), dict)
                and evidence[field_name].get("origin") == "deterministic"
                and evidence[field_name].get("value") == value
                and isinstance(evidence[field_name].get("evidence"), str)
                and bool(evidence[field_name]["evidence"].strip())
                and normalize_evidence(
                    evidence[field_name]["evidence"]
                ) in normalize_evidence(source)
                and verify_value(
                    field_name,
                    value,
                    evidence[field_name]["evidence"],
                ) is None
                for field_name, value in specs.items()
            )

            if has_verified_specs:
                continue

        if issue.resolved:
            continue

        report.add(
            code=issue.code,
            severity="error",
            field_name=issue.field,
            message=issue.message,
        )

    # 2. Unabhängige Quellenbefunde
    for finding in source_findings:
        report.add(
            code=finding["code"],
            severity=(
                "error"
                if finding["code"] == "CONFLICTING_VALUES"
                else "warning"
            ),
            field_name=finding.get("field"),
            message=str(finding),
            details=finding,
        )

    # 3. Finale Feldkonsistenz
    field_review = evaluate_final_fields(specs, evidence)

    existing = {
        (finding.code, finding.field)
        for finding in report.findings
    }

    for finding in field_review.findings:
        key = (finding.code, finding.field)

        if key in existing:
            continue

        report.findings.append(finding)
        existing.add(key)

    # 4. Semantische Prüfung ausgewählter GPU-Felder
    semantic_review = evaluate_gpu_evidence(
        specs,
        evidence,
        source,
    )

    report.findings.extend(semantic_review.findings)

    # Doppelte Befunde aus unterschiedlichen Prüfphasen zusammenführen.
    unique_findings = []
    seen = set()

    for finding in report.findings:
        key = (finding.code, finding.field)

        if key in seen:
            continue

        seen.add(key)
        unique_findings.append(finding)

    report.findings = unique_findings
    return report

def resolve_validation_issues(
    validation_issues: list[ValidationIssue],
    specs: dict,
    evidence: dict,
    source: str,
) -> list[ValidationIssue]:
    """Markiert eindeutig korrigierte Ganzzahl-Felder als behoben."""

    import re

    for issue in validation_issues:
        if issue.field is None:
            continue

        if issue.code not in {
            "FIELD_MISSING",
            "INVALID_VALUE",
            "EVIDENCE_NOT_FOUND",
            "VALUE_VERIFICATION_FAILED",
        }:
            continue

        value = specs.get(issue.field)
        item = evidence.get(issue.field)

        if not isinstance(item, dict):
            continue

        if item.get("origin") != "deterministic":
            continue

        # Listen nur für die explizit geprüfte API-Unterstützung zulassen.
        if issue.field == "api_support":
            if issue.code != "EVIDENCE_NOT_FOUND":
                continue

            if item.get("value") != value:
                continue

            if not verify_api_support_evidence(
                value,
                item.get("evidence"),
                source,
            ):
                continue

            issue.resolved = True
            continue

        # Alle übrigen Felder bleiben auf Ganzzahlen beschränkt.
        if type(value) is not int:
            continue

        if item.get("value") != value:
            continue

        source_evidence = item.get("evidence", "")

        if not isinstance(source_evidence, str):
            continue

        normalized_source = " ".join(source.split()).casefold()
        normalized_evidence = " ".join(source_evidence.split()).casefold()

        if not normalized_evidence:
            continue

        if normalized_evidence not in normalized_source:
            continue

        # Dieselben feldspezifischen Regeln wie bei der Extraktion.
        if verify_value(
            issue.field,
            value,
            source_evidence,
        ) is not None:
            continue

        issue.resolved = True

    return validation_issues