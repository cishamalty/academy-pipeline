"""
validate.py — Schema and data validation

Responsibilities:
- Validate that required columns exist in each source DataFrame
- Validate that the join key (email) is present before any merge
- Check for completely empty DataFrames
- Report validation results clearly — never fail silently
- Raise hard errors for critical failures (missing join key)
- Log warnings for non-critical issues (high null rates, unexpected values)

Runs BEFORE cleaning. If validation fails, the pipeline stops with a clear
message rather than producing corrupted output downstream.
"""

import logging
from dataclasses import dataclass, field

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    """Result of a single validation check."""
    check: str
    passed: bool
    message: str
    severity: str = "error"  # "error" | "warning" | "info"


@dataclass
class ValidationReport:
    """Aggregated results for a full validation run."""
    source: str
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.severity == "error")

    @property
    def errors(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed and r.severity == "error"]

    @property
    def warnings(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed and r.severity == "warning"]

    def summary(self) -> str:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        return (
            f"{self.source}: {passed}/{total} checks passed | "
            f"{len(self.errors)} error(s) | {len(self.warnings)} warning(s)"
        )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_not_empty(df: pd.DataFrame, source: str) -> ValidationResult:
    """Fail if the DataFrame has no rows."""
    passed = len(df) > 0
    return ValidationResult(
        check="not_empty",
        passed=passed,
        message=f"{source}: DataFrame is empty" if not passed else f"{source}: {len(df)} rows found",
        severity="error"
    )


def check_join_key(df: pd.DataFrame, source: str, join_key: str = "email") -> ValidationResult:
    """Fail if the join key column is missing — merges cannot proceed without it."""
    passed = join_key in df.columns
    return ValidationResult(
        check="join_key_present",
        passed=passed,
        message=(
            f"{source}: join key '{join_key}' is missing — cannot merge"
            if not passed
            else f"{source}: join key '{join_key}' present"
        ),
        severity="error"
    )


def check_required_columns(
    df: pd.DataFrame, source: str, required: list[str]
) -> ValidationResult:
    """Warn if expected columns are missing (non-critical — some may come from merges)."""
    missing = [c for c in required if c not in df.columns]
    passed = len(missing) == 0
    return ValidationResult(
        check="required_columns",
        passed=passed,
        message=(
            f"{source}: missing columns — {missing}"
            if not passed
            else f"{source}: all required columns present"
        ),
        severity="warning"
    )


def check_null_rate(
    df: pd.DataFrame, source: str, column: str, threshold: float = 0.5
) -> ValidationResult:
    """Warn if a column has more than threshold% nulls."""
    if column not in df.columns:
        return ValidationResult(
            check=f"null_rate_{column}",
            passed=True,
            message=f"{source}: column '{column}' not present — null check skipped",
            severity="info"
        )
    null_rate = df[column].isna().mean()
    passed = null_rate <= threshold
    return ValidationResult(
        check=f"null_rate_{column}",
        passed=passed,
        message=(
            f"{source}: '{column}' has {null_rate:.1%} nulls (threshold: {threshold:.0%})"
            if not passed
            else f"{source}: '{column}' null rate {null_rate:.1%} — within threshold"
        ),
        severity="warning"
    )


def check_duplicate_emails(df: pd.DataFrame, source: str) -> ValidationResult:
    """Warn if duplicate emails exist before deduplication."""
    if "email" not in df.columns:
        return ValidationResult(
            check="duplicate_emails",
            passed=True,
            message=f"{source}: no email column — duplicate check skipped",
            severity="info"
        )
    total = len(df)
    unique = df["email"].nunique()
    duplicates = total - unique
    passed = duplicates == 0
    return ValidationResult(
        check="duplicate_emails",
        passed=passed,
        message=(
            f"{source}: {duplicates} duplicate email(s) found — will be removed during cleaning"
            if not passed
            else f"{source}: no duplicate emails"
        ),
        severity="warning"
    )


def check_survey_response_columns(
    df: pd.DataFrame, source: str, response_mapping: dict
) -> ValidationResult:
    """Check that the expected survey response columns exist in the assessment file."""
    expected = [v for v in response_mapping.values() if v is not None]
    missing = [c for c in expected if c not in df.columns]
    passed = len(missing) == 0
    return ValidationResult(
        check="survey_response_columns",
        passed=passed,
        message=(
            f"{source}: survey response column(s) missing — {missing}"
            if not passed
            else f"{source}: all survey response columns present"
        ),
        severity="warning"
    )


# ---------------------------------------------------------------------------
# Full validation runner
# ---------------------------------------------------------------------------

def validate_source(
    df: pd.DataFrame | None,
    source_name: str,
    join_key: str = "email",
    required_columns: list[str] | None = None,
    survey_response_mapping: dict | None = None,
    null_check_columns: list[str] | None = None,
    null_threshold: float = 0.5,
) -> ValidationReport:
    """
    Run all applicable checks on a single source DataFrame.
    Returns a ValidationReport — does not raise on its own.
    """
    report = ValidationReport(source=source_name)

    if df is None:
        report.results.append(ValidationResult(
            check="dataframe_present",
            passed=False,
            message=f"{source_name}: DataFrame is None — source file was not loaded",
            severity="error"
        ))
        return report

    report.results.append(check_not_empty(df, source_name))
    report.results.append(check_join_key(df, source_name, join_key))
    report.results.append(check_duplicate_emails(df, source_name))

    if required_columns:
        report.results.append(check_required_columns(df, source_name, required_columns))

    if survey_response_mapping:
        report.results.append(check_survey_response_columns(df, source_name, survey_response_mapping))

    for col in (null_check_columns or []):
        report.results.append(check_null_rate(df, source_name, col, null_threshold))

    return report


def validate_all(
    data: dict[str, pd.DataFrame | None],
    course_config: dict,
    base_config: dict,
) -> list[ValidationReport]:
    """
    Validate all loaded DataFrames for a course.
    Raises RuntimeError if any critical (error-level) check fails.
    """
    join_key = base_config.get("join_key", "email")
    response_mapping = course_config.get("survey_response_mapping", {})
    reports = []

    source_checks = {
        "post_course": {
            "required_columns": [join_key],
            "survey_response_mapping": response_mapping,
            "null_check_columns": ["email"],
        },
        "pre_course": {
            "required_columns": [join_key],
            "null_check_columns": ["email"],
        },
        "progress": {
            "required_columns": [join_key, "Completed At"],
            "null_check_columns": ["email"],
        },
        "user_export": {
            "required_columns": [join_key],
            "null_check_columns": ["email"],
        },
        "master_reference": {
            "required_columns": [join_key],
            "null_check_columns": ["email"],
        },
    }

    for source_name, df in data.items():
        if df is None:
            # None is expected for optional sources — only log, don't error
            logger.info(f"Skipping validation for '{source_name}' — not loaded")
            continue

        checks = source_checks.get(source_name, {})
        report = validate_source(
            df=df,
            source_name=source_name,
            join_key=join_key,
            **checks
        )
        reports.append(report)

        # Log the summary
        logger.info(report.summary())
        for r in report.warnings:
            logger.warning(r.message)
        for r in report.errors:
            logger.error(r.message)

    # Hard stop if any critical errors found
    all_errors = [e for rep in reports for e in rep.errors]
    if all_errors:
        error_messages = "\n".join(f"  - {e.message}" for e in all_errors)
        raise RuntimeError(
            f"Validation failed for course '{course_config.get('course_name')}' "
            f"— pipeline cannot continue:\n{error_messages}"
        )

    logger.info(f"All validations passed for {course_config.get('course_name')}")
    return reports
