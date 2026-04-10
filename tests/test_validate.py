"""
test_validate.py — Unit tests for src/validate.py
"""

import pandas as pd
import pytest

from src.validate import (
    ValidationReport,
    check_duplicate_emails,
    check_join_key,
    check_not_empty,
    check_null_rate,
    check_required_columns,
    check_survey_response_columns,
    validate_all,
    validate_source,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_config():
    return {
        "join_key": "email",
        "email_columns": ["email", "Email", "Student Email"],
    }


@pytest.fixture
def course_config():
    return {
        "course_name": "Business Compliance",
        "course_key": "compliance",
        "has_pre_course": True,
        "survey_response_mapping": {
            "gender": "Response.1",
            "age_group": "Response.2",
            "hub": "Response.5",
            "district": None,
        },
    }


@pytest.fixture
def good_df():
    return pd.DataFrame({
        "email": ["a@b.com", "c@d.com", "e@f.com"],
        "Response.1": ["Male", "Female", "Male"],
        "Response.2": ["18-24", "25-35", "36+"],
        "Response.5": ["Outbox", "Miic", "Sbil"],
        "Completed At": ["2026-04-01", "2026-04-02", "2026-04-03"],
    })


# ---------------------------------------------------------------------------
# check_not_empty
# ---------------------------------------------------------------------------

class TestCheckNotEmpty:
    def test_empty_dataframe_fails(self):
        r = check_not_empty(pd.DataFrame(), "source")
        assert not r.passed
        assert r.severity == "error"

    def test_non_empty_passes(self):
        r = check_not_empty(pd.DataFrame({"a": [1]}), "source")
        assert r.passed


# ---------------------------------------------------------------------------
# check_join_key
# ---------------------------------------------------------------------------

class TestCheckJoinKey:
    def test_missing_email_fails(self):
        df = pd.DataFrame({"name": ["Alice"]})
        r = check_join_key(df, "source", "email")
        assert not r.passed
        assert r.severity == "error"

    def test_email_present_passes(self):
        df = pd.DataFrame({"email": ["a@b.com"]})
        r = check_join_key(df, "source", "email")
        assert r.passed


# ---------------------------------------------------------------------------
# check_required_columns
# ---------------------------------------------------------------------------

class TestCheckRequiredColumns:
    def test_missing_columns_warns(self):
        df = pd.DataFrame({"email": ["a@b.com"]})
        r = check_required_columns(df, "source", ["email", "name", "dob"])
        assert not r.passed
        assert r.severity == "warning"
        assert "name" in r.message
        assert "dob" in r.message

    def test_all_present_passes(self):
        df = pd.DataFrame({"email": ["a@b.com"], "name": ["Alice"]})
        r = check_required_columns(df, "source", ["email", "name"])
        assert r.passed


# ---------------------------------------------------------------------------
# check_null_rate
# ---------------------------------------------------------------------------

class TestCheckNullRate:
    def test_high_null_rate_warns(self):
        df = pd.DataFrame({"email": [None] * 8 + ["a@b.com", "c@d.com"]})
        r = check_null_rate(df, "source", "email", threshold=0.5)
        assert not r.passed
        assert r.severity == "warning"

    def test_acceptable_null_rate_passes(self):
        df = pd.DataFrame({"email": ["a@b.com"] * 9 + [None]})
        r = check_null_rate(df, "source", "email", threshold=0.5)
        assert r.passed

    def test_missing_column_skips(self):
        df = pd.DataFrame({"name": ["Alice"]})
        r = check_null_rate(df, "source", "email")
        assert r.passed
        assert r.severity == "info"


# ---------------------------------------------------------------------------
# check_duplicate_emails
# ---------------------------------------------------------------------------

class TestCheckDuplicateEmails:
    def test_duplicates_warn(self):
        df = pd.DataFrame({"email": ["a@b.com", "a@b.com", "c@d.com"]})
        r = check_duplicate_emails(df, "source")
        assert not r.passed
        assert r.severity == "warning"
        assert "1" in r.message

    def test_no_duplicates_passes(self):
        df = pd.DataFrame({"email": ["a@b.com", "c@d.com"]})
        r = check_duplicate_emails(df, "source")
        assert r.passed

    def test_no_email_column_skips(self):
        df = pd.DataFrame({"name": ["Alice"]})
        r = check_duplicate_emails(df, "source")
        assert r.passed
        assert r.severity == "info"


# ---------------------------------------------------------------------------
# check_survey_response_columns
# ---------------------------------------------------------------------------

class TestCheckSurveyResponseColumns:
    def test_missing_response_column_warns(self):
        df = pd.DataFrame({"email": ["a@b.com"], "Response.1": ["Male"]})
        mapping = {"gender": "Response.1", "hub": "Response.5"}
        r = check_survey_response_columns(df, "source", mapping)
        assert not r.passed
        assert "Response.5" in r.message

    def test_all_response_columns_present_passes(self):
        df = pd.DataFrame({
            "email": ["a@b.com"],
            "Response.1": ["Male"],
            "Response.5": ["Outbox"],
        })
        mapping = {"gender": "Response.1", "hub": "Response.5"}
        r = check_survey_response_columns(df, "source", mapping)
        assert r.passed

    def test_null_mapping_values_ignored(self):
        df = pd.DataFrame({"email": ["a@b.com"], "Response.1": ["Male"]})
        mapping = {"gender": "Response.1", "district": None}
        r = check_survey_response_columns(df, "source", mapping)
        assert r.passed


# ---------------------------------------------------------------------------
# validate_source
# ---------------------------------------------------------------------------

class TestValidateSource:
    def test_none_dataframe_fails(self):
        report = validate_source(None, "source")
        assert not report.passed
        assert len(report.errors) == 1

    def test_good_dataframe_passes(self, good_df):
        report = validate_source(good_df, "source")
        assert report.passed

    def test_report_has_summary(self, good_df):
        report = validate_source(good_df, "source")
        summary = report.summary()
        assert "source" in summary
        assert "passed" in summary


# ---------------------------------------------------------------------------
# ValidationReport
# ---------------------------------------------------------------------------

class TestValidationReport:
    def test_passed_when_no_errors(self):
        from src.validate import ValidationResult
        report = ValidationReport(source="test")
        report.results.append(
            ValidationResult("check1", True, "all good", "error")
        )
        assert report.passed

    def test_failed_when_error_present(self):
        from src.validate import ValidationResult
        report = ValidationReport(source="test")
        report.results.append(
            ValidationResult("check1", False, "bad", "error")
        )
        assert not report.passed

    def test_warnings_do_not_fail_report(self):
        from src.validate import ValidationResult
        report = ValidationReport(source="test")
        report.results.append(
            ValidationResult("check1", False, "warning only", "warning")
        )
        assert report.passed


# ---------------------------------------------------------------------------
# validate_all
# ---------------------------------------------------------------------------

class TestValidateAll:
    def test_raises_on_critical_failure(self, base_config, course_config):
        data = {
            "post_course": pd.DataFrame(),  # empty — critical failure
            "pre_course": None,
            "progress": None,
            "user_export": None,
            "master_reference": None,
        }
        with pytest.raises(RuntimeError, match="Validation failed"):
            validate_all(data, course_config, base_config)

    def test_passes_on_good_data(self, good_df, base_config, course_config):
        data = {
            "post_course": good_df,
            "pre_course": None,
            "progress": None,
            "user_export": None,
            "master_reference": None,
        }
        reports = validate_all(data, course_config, base_config)
        assert len(reports) == 1
        assert reports[0].passed

    def test_none_sources_skipped(self, good_df, base_config, course_config):
        data = {
            "post_course": good_df,
            "pre_course": None,
            "progress": None,
            "user_export": None,
            "master_reference": None,
        }
        reports = validate_all(data, course_config, base_config)
        # Only post_course was loaded — only one report
        assert len(reports) == 1
