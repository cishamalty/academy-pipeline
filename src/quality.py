"""
quality.py — Data quality checks and reporting

Responsibilities:
- Run assertions on the cleaned DataFrame before export
- Measure key quality metrics (null rates, value distributions, row counts)
- Generate a human-readable quality report per run
- Write the report to the reports/ folder as JSON and plain text
- Never silently pass bad data to stakeholders

Quality checks are split into two tiers:
  - CRITICAL: pipeline stops if these fail (e.g. empty output, missing join key)
  - WARNING:  pipeline continues but report flags the issue
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class QualityCheck:
    """Result of a single quality check on the cleaned DataFrame."""
    check: str
    passed: bool
    message: str
    severity: str = "warning"   # "critical" | "warning" | "info"
    value: float | int | str | None = None


@dataclass
class QualityReport:
    """Full quality report for one pipeline run."""
    course_name: str
    run_timestamp: str
    input_rows: int
    output_rows: int
    rows_dropped: int
    checks: list[QualityCheck] = field(default_factory=list)
    column_stats: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks if c.severity == "critical")

    @property
    def critical_failures(self) -> list[QualityCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "critical"]

    @property
    def warnings(self) -> list[QualityCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Individual quality checks
# ---------------------------------------------------------------------------

def check_output_not_empty(df: pd.DataFrame) -> QualityCheck:
    passed = len(df) > 0
    return QualityCheck(
        check="output_not_empty",
        passed=passed,
        message="Output DataFrame is empty — nothing to export" if not passed
                else f"Output has {len(df)} rows",
        severity="critical",
        value=len(df)
    )


def check_minimum_rows(df: pd.DataFrame, minimum: int = 10) -> QualityCheck:
    passed = len(df) >= minimum
    return QualityCheck(
        check="minimum_rows",
        passed=passed,
        message=f"Output has only {len(df)} rows — expected at least {minimum}" if not passed
                else f"Row count {len(df)} meets minimum of {minimum}",
        severity="warning",
        value=len(df)
    )


def check_no_duplicate_emails(df: pd.DataFrame) -> QualityCheck:
    if "email" not in df.columns:
        return QualityCheck(
            check="no_duplicate_emails",
            passed=True,
            message="No email column — duplicate check skipped",
            severity="info"
        )
    dupes = df["email"].duplicated().sum()
    passed = dupes == 0
    return QualityCheck(
        check="no_duplicate_emails",
        passed=passed,
        message=f"{dupes} duplicate email(s) remain after cleaning" if not passed
                else "No duplicate emails in output",
        severity="critical",
        value=int(dupes)
    )


def check_email_null_rate(df: pd.DataFrame, threshold: float = 0.05) -> QualityCheck:
    if "email" not in df.columns:
        return QualityCheck(
            check="email_null_rate",
            passed=True,
            message="No email column — null check skipped",
            severity="info"
        )
    null_rate = df["email"].isna().mean()
    passed = null_rate <= threshold
    return QualityCheck(
        check="email_null_rate",
        passed=passed,
        message=f"Email null rate {null_rate:.1%} exceeds threshold {threshold:.0%}" if not passed
                else f"Email null rate {null_rate:.1%} is within threshold",
        severity="warning",
        value=round(null_rate, 4)
    )


def check_hub_coverage(df: pd.DataFrame, valid_hubs: list[str]) -> QualityCheck:
    if "ESO Hub" not in df.columns:
        return QualityCheck(
            check="hub_coverage",
            passed=True,
            message="No ESO Hub column — hub check skipped",
            severity="info"
        )
    unassigned = (df["ESO Hub"] == "Not Assigned").sum()
    unassigned_rate = unassigned / len(df) if len(df) > 0 else 0
    unknown = df[~df["ESO Hub"].isin(valid_hubs + ["Not Assigned"])]["ESO Hub"].unique().tolist()
    passed = len(unknown) == 0
    return QualityCheck(
        check="hub_coverage",
        passed=passed,
        message=f"Unknown hub values found: {unknown}" if not passed
                else f"All hub values are valid. {unassigned} ({unassigned_rate:.1%}) Not Assigned",
        severity="warning",
        value=unassigned_rate
    )


def check_gender_coverage(df: pd.DataFrame, valid_values: list[str]) -> QualityCheck:
    if "Gender" not in df.columns:
        return QualityCheck(
            check="gender_coverage",
            passed=True,
            message="No Gender column — coverage check skipped",
            severity="info"
        )
    unspecified = (df["Gender"] == "Not Specified").sum()
    unspecified_rate = unspecified / len(df) if len(df) > 0 else 0
    threshold = 0.3
    passed = unspecified_rate <= threshold
    return QualityCheck(
        check="gender_coverage",
        passed=passed,
        message=f"{unspecified_rate:.1%} of Gender values are 'Not Specified' (threshold: {threshold:.0%})" if not passed
                else f"Gender coverage OK — {unspecified_rate:.1%} Not Specified",
        severity="warning",
        value=round(unspecified_rate, 4)
    )


def check_completion_column(df: pd.DataFrame) -> QualityCheck:
    col = next((c for c in df.columns if "% completed" in c.lower()), None)
    if not col:
        return QualityCheck(
            check="completion_column",
            passed=True,
            message="No % Completed column — check skipped",
            severity="info"
        )
    null_rate = df[col].isna().mean()
    passed = null_rate <= 0.1
    return QualityCheck(
        check="completion_column",
        passed=passed,
        message=f"% Completed has {null_rate:.1%} nulls — expected < 10%" if not passed
                else f"% Completed null rate {null_rate:.1%} is acceptable",
        severity="warning",
        value=round(null_rate, 4)
    )


def check_required_output_columns(
    df: pd.DataFrame,
    required: list[str] | None = None
) -> QualityCheck:
    default_required = ["email", "Full Name", "Gender", "Age group", "ESO Hub", "% Completed"]
    cols_to_check = required or default_required
    missing = [c for c in cols_to_check if c not in df.columns]
    passed = len(missing) == 0
    return QualityCheck(
        check="required_output_columns",
        passed=passed,
        message=f"Output missing expected columns: {missing}" if not passed
                else "All expected output columns present",
        severity="warning",
        value=str(missing) if missing else None
    )


# ---------------------------------------------------------------------------
# Column statistics
# ---------------------------------------------------------------------------

def compute_column_stats(df: pd.DataFrame) -> dict:
    """
    Compute summary statistics for key columns.
    These appear in the quality report so stakeholders can
    spot distributional issues at a glance.
    """
    stats = {}
    stats["total_rows"] = len(df)

    # Null rates for every column
    stats["null_rates"] = {
        col: round(df[col].isna().mean(), 4)
        for col in df.columns
    }

    # Value distributions for categorical columns
    categorical_cols = ["Gender", "Age group", "ESO Hub", "Region",
                        "DISABILITY", "NATIONALITY", "Quarter",
                        "% Completed Category", "email_status"]
    stats["distributions"] = {}
    for col in categorical_cols:
        if col in df.columns:
            dist = df[col].value_counts(dropna=False).to_dict()
            stats["distributions"][col] = {str(k): int(v) for k, v in dist.items()}

    # Completion stats
    completion_col = next(
        (c for c in df.columns if c.lower() == "% completed"), None
    )
    if completion_col:
        numeric = pd.to_numeric(df[completion_col], errors="coerce")
        stats["completion"] = {
            "mean": round(numeric.mean(), 2) if not numeric.isna().all() else None,
            "completed_100pct": int((numeric == 100).sum()),
            "completed_0pct": int((numeric == 0).sum()),
        }

    # Email validation stats
    if "email_status" in df.columns:
        stats["email_validation"] = df["email_status"].value_counts().to_dict()

    return stats


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_report(report: QualityReport, reports_dir: str) -> str:
    """
    Write the quality report to the reports/ folder.
    Creates two files:
      - reports/{course}_{timestamp}.json  — machine-readable
      - reports/{course}_{timestamp}.txt   — human-readable summary
    Returns the path to the text report.
    """
    os.makedirs(reports_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    course_key = report.course_name.lower().replace(" ", "_")
    base_name = f"{course_key}_{timestamp}"

    # JSON report
    json_path = os.path.join(reports_dir, f"{base_name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)

    # Text report
    txt_path = os.path.join(reports_dir, f"{base_name}.txt")
    lines = [
        f"QUALITY REPORT — {report.course_name}",
        f"Run at: {report.run_timestamp}",
        "=" * 60,
        f"Input rows:   {report.input_rows}",
        f"Output rows:  {report.output_rows}",
        f"Rows dropped: {report.rows_dropped}",
        "",
        "CHECKS",
        "-" * 40,
    ]
    for c in report.checks:
        status = "PASS" if c.passed else f"FAIL [{c.severity.upper()}]"
        lines.append(f"  [{status}] {c.check}: {c.message}")

    lines += ["", "COLUMN STATISTICS", "-" * 40]

    # Null rates
    lines.append("Null rates:")
    for col, rate in report.column_stats.get("null_rates", {}).items():
        if rate > 0:
            lines.append(f"  {col}: {rate:.1%}")

    # Distributions
    lines.append("")
    lines.append("Value distributions:")
    for col, dist in report.column_stats.get("distributions", {}).items():
        lines.append(f"  {col}:")
        for val, count in sorted(dist.items(), key=lambda x: -x[1]):
            lines.append(f"    {val}: {count}")

    # Overall result
    lines += [
        "",
        "=" * 60,
        f"RESULT: {'PASSED' if report.passed else 'FAILED'}",
        f"Critical failures: {len(report.critical_failures)}",
        f"Warnings: {len(report.warnings)}",
    ]

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"Quality report written to {txt_path}")
    return txt_path


# ---------------------------------------------------------------------------
# Master quality runner
# ---------------------------------------------------------------------------

def run_quality_checks(
    df_input: pd.DataFrame,
    df_output: pd.DataFrame,
    course_config: dict,
    base_config: dict,
    reports_dir: str = "reports",
) -> QualityReport:
    """
    Run all quality checks on the cleaned output DataFrame.
    Writes report to disk.
    Raises RuntimeError if any critical check fails.

    Args:
        df_input:      DataFrame before cleaning (for row count comparison)
        df_output:     DataFrame after cleaning (what gets exported)
        course_config: Per-course config dict
        base_config:   Shared base config dict
        reports_dir:   Folder to write reports into

    Returns:
        QualityReport
    """
    course_name = course_config.get("course_name", "Unknown")
    valid_hubs = base_config.get("hubs", {}).get("valid", [])
    valid_gender = base_config.get("gender", {}).get("valid_values", [])

    report = QualityReport(
        course_name=course_name,
        run_timestamp=datetime.now().isoformat(),
        input_rows=len(df_input),
        output_rows=len(df_output),
        rows_dropped=len(df_input) - len(df_output),
    )

    # Run all checks
    report.checks = [
        check_output_not_empty(df_output),
        check_minimum_rows(df_output),
        check_no_duplicate_emails(df_output),
        check_email_null_rate(df_output),
        check_hub_coverage(df_output, valid_hubs),
        check_gender_coverage(df_output, valid_gender),
        check_completion_column(df_output),
        check_required_output_columns(df_output),
    ]

    # Compute column statistics
    report.column_stats = compute_column_stats(df_output)

    # Log summary
    passed = sum(1 for c in report.checks if c.passed)
    total = len(report.checks)
    logger.info(f"Quality checks: {passed}/{total} passed for '{course_name}'")
    for c in report.critical_failures:
        logger.error(f"CRITICAL: {c.message}")
    for c in report.warnings:
        logger.warning(f"WARNING: {c.message}")

    # Write report to disk
    write_report(report, reports_dir)

    # Hard stop on critical failures
    if not report.passed:
        failures = "\n".join(f"  - {c.message}" for c in report.critical_failures)
        raise RuntimeError(
            f"Quality checks failed for '{course_name}' — export blocked:\n{failures}"
        )

    return report
