"""
test_clean.py — Unit tests for src/clean.py

Every cleaning function gets its own test class.
Tests cover: happy path, edge cases, null inputs, config-driven behaviour.
"""

from datetime import date

import pandas as pd
import pytest

from src.clean import (
    assign_quarter,
    assign_region,
    build_full_name,
    calculate_age,
    categorise_disability,
    clean_date,
    clean_email,
    clean_email_column,
    deduplicate,
    normalise_age_group,
    normalise_gender,
    normalise_hub,
    resolve_merge_conflicts,
    validate_email,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def gender_config():
    return {
        "gender": {
            "valid_values": ["Male", "Female", "Other", "Prefer not to say"],
            "mappings": {
                "male": "Male",
                "m": "Male",
                "1": "Male",
                "female": "Female",
                "f": "Female",
                "2": "Female",
                "other": "Other",
            },
        }
    }


@pytest.fixture
def hub_config():
    return {
        "hubs": {
            "valid": ["Outbox", "Miic", "Sbil", "Witu", "Mubs-Eiic", "Not Assigned"],
            "mappings": {
                "outbox": "Outbox",
                "outbox hub": "Outbox",
                "miic": "Miic",
                "miic hub": "Miic",
                "sbil": "Sbil",
                "stanbic": "Sbil",
                "stanbic business incubator": "Sbil",
                "witu": "Witu",
                "women in tech": "Witu",
                "mubs": "Mubs-Eiic",
                "mubs-eiic": "Mubs-Eiic",
                "not assigned": "Not Assigned",
                "": "Not Assigned",
            },
        }
    }


@pytest.fixture
def age_config():
    return {
        "age_bins": {
            "labels": ["Below 18", "18-24", "25-35", "36+", "Not Assigned"],
            "mappings": {
                "below 18 years": "Below 18",
                "18-24 years": "18-24",
                "between 18 to 24": "18-24",
                "25-35 years": "25-35",
                "between 25 to 35": "25-35",
                "36+ years": "36+",
                "between 36 to 45": "36+",
                "above 45": "36+",
                "above 45 years": "36+",
                "not assigned": "Not Assigned",
                "": "Not Assigned",
            },
        }
    }


@pytest.fixture
def region_config():
    return {
        "regions": {
            "Central": ["Kampala", "Wakiso", "Mukono"],
            "Eastern": ["Jinja", "Mbale", "Tororo"],
            "Northern": ["Gulu", "Lira", "Arua"],
            "Western": ["Mbarara", "Kabale", "Kasese"],
        }
    }


@pytest.fixture
def disability_config():
    return {
        "disability": {
            "default": "Not Disabled",
            "categories": {
                "Visual Impairment": ["blind", "visual", "sight", "low vision"],
                "Hearing Impairment": ["deaf", "hearing", "mute"],
                "Physical Disability": ["physical", "mobility", "wheelchair", "amputee"],
                "Not Disabled": ["none", "no", "not applicable", "n/a", "not disabled", ""],
            },
        }
    }


@pytest.fixture
def quarter_mapping():
    return {
        "quarter_mapping": {
            "2024-01": "Y4Q3",
            "2024-04": "Y4Q4",
            "2025-07": "Y6Q1",
            "2026-04": "Y6Q4",
        }
    }


@pytest.fixture
def email_validation_config():
    return {
        "email_validation": {
            "disposable_domains": ["mailinator.com", "tempmail.org", "yopmail.com"],
            "domain_typos": {
                "gmial.com": "gmail.com",
                "gmai.com": "gmail.com",
                "yahooo.com": "yahoo.com",
            },
            "fake_keywords": ["test", "demo", "fake", "dummy"],
            "risk_score_threshold": 5,
        }
    }


# ---------------------------------------------------------------------------
# Email cleaning
# ---------------------------------------------------------------------------

class TestCleanEmail:
    def test_strips_whitespace(self):
        assert clean_email("  martin@gmail.com  ") == "martin@gmail.com"

    def test_lowercases(self):
        assert clean_email("MARTIN@GMAIL.COM") == "martin@gmail.com"

    def test_strips_and_lowercases(self):
        assert clean_email("  TEST@Gmail.COM  ") == "test@gmail.com"

    def test_none_returns_none(self):
        assert clean_email(None) is None

    def test_nan_returns_none(self):
        assert clean_email(float("nan")) is None

    def test_empty_string_returns_none(self):
        assert clean_email("   ") is None

    def test_non_string_returns_none(self):
        assert clean_email(12345) is None


class TestCleanEmailColumn:
    def test_cleans_entire_column(self):
        df = pd.DataFrame({"email": ["  A@B.COM  ", "c@D.com", None]})
        result = clean_email_column(df)
        assert result["email"].iloc[0] == "a@b.com"
        assert result["email"].iloc[1] == "c@d.com"
        assert pd.isna(result["email"].iloc[2])

    def test_missing_column_returns_unchanged(self):
        df = pd.DataFrame({"name": ["Alice"]})
        result = clean_email_column(df)
        assert "email" not in result.columns


# ---------------------------------------------------------------------------
# Date cleaning
# ---------------------------------------------------------------------------

class TestCleanDate:
    def test_iso_format(self):
        assert clean_date("2024-01-15") == date(2024, 1, 15)

    def test_slash_dmy_format(self):
        assert clean_date("15/01/2024") == date(2024, 1, 15)

    def test_slash_mdy_format(self):
        assert clean_date("01/15/2024") == date(2024, 1, 15)

    def test_garbage_returns_none(self):
        assert clean_date("garbage") is None

    def test_none_returns_none(self):
        assert clean_date(None) is None

    def test_nan_returns_none(self):
        assert clean_date(float("nan")) is None

    def test_empty_string_returns_none(self):
        assert clean_date("") is None


# ---------------------------------------------------------------------------
# Age calculation
# ---------------------------------------------------------------------------

class TestCalculateAge:
    def test_standard_age(self):
        assert calculate_age(date(2000, 1, 1), date(2026, 1, 1)) == 26

    def test_birthday_not_yet_this_year(self):
        assert calculate_age(date(2000, 12, 31), date(2026, 1, 1)) == 25

    def test_none_dob_returns_none(self):
        assert calculate_age(None) is None

    def test_future_dob_returns_none(self):
        assert calculate_age(date(2030, 1, 1), date(2026, 1, 1)) is None

    def test_unrealistic_age_returns_none(self):
        assert calculate_age(date(1800, 1, 1), date(2026, 1, 1)) is None


# ---------------------------------------------------------------------------
# Gender normalisation
# ---------------------------------------------------------------------------

class TestNormaliseGender:
    def test_male_lowercase(self, gender_config):
        cfg = gender_config["gender"]
        assert normalise_gender("male", cfg["mappings"], cfg["valid_values"]) == "Male"

    def test_female_uppercase(self, gender_config):
        cfg = gender_config["gender"]
        assert normalise_gender("FEMALE", cfg["mappings"], cfg["valid_values"]) == "Female"

    def test_single_letter_m(self, gender_config):
        cfg = gender_config["gender"]
        assert normalise_gender("m", cfg["mappings"], cfg["valid_values"]) == "Male"

    def test_luganda_mukyala(self, gender_config):
        cfg = gender_config["gender"]
        extra = {"mukyala": "Female", "mwami": "Male"}
        combined = {**cfg["mappings"], **{k.lower(): v for k, v in extra.items()}}
        assert normalise_gender("Mukyala", combined, cfg["valid_values"]) == "Female"

    def test_luganda_mwami(self, gender_config):
        cfg = gender_config["gender"]
        extra = {"mwami": "Male"}
        combined = {**cfg["mappings"], **{k.lower(): v for k, v in extra.items()}}
        assert normalise_gender("Mwami", combined, cfg["valid_values"]) == "Male"

    def test_unknown_value_returns_not_specified(self, gender_config):
        cfg = gender_config["gender"]
        assert normalise_gender("xyz", cfg["mappings"], cfg["valid_values"]) == "Not Specified"

    def test_none_returns_not_specified(self, gender_config):
        cfg = gender_config["gender"]
        assert normalise_gender(None, cfg["mappings"], cfg["valid_values"]) == "Not Specified"

    def test_already_valid(self, gender_config):
        cfg = gender_config["gender"]
        assert normalise_gender("Female", cfg["mappings"], cfg["valid_values"]) == "Female"


# ---------------------------------------------------------------------------
# Age group normalisation
# ---------------------------------------------------------------------------

class TestNormaliseAgeGroup:
    def test_standard_mapping(self, age_config):
        mappings = age_config["age_bins"]["mappings"]
        assert normalise_age_group("18-24 years", mappings) == "18-24"

    def test_between_format(self, age_config):
        mappings = age_config["age_bins"]["mappings"]
        assert normalise_age_group("between 25 to 35", mappings) == "25-35"

    def test_above_45_maps_to_36_plus(self, age_config):
        mappings = age_config["age_bins"]["mappings"]
        assert normalise_age_group("above 45", mappings) == "36+"

    def test_luganda_18_24(self, age_config):
        mappings = {**age_config["age_bins"]["mappings"],
                    "wakati wa myaka 18 ne 24": "18-24"}
        assert normalise_age_group("Wakati wa myaka 18 ne 24", mappings) == "18-24"

    def test_none_returns_not_assigned(self, age_config):
        mappings = age_config["age_bins"]["mappings"]
        assert normalise_age_group(None, mappings) == "Not Assigned"

    def test_empty_returns_not_assigned(self, age_config):
        mappings = age_config["age_bins"]["mappings"]
        assert normalise_age_group("", mappings) == "Not Assigned"

    def test_already_valid(self, age_config):
        mappings = age_config["age_bins"]["mappings"]
        assert normalise_age_group("25-35", mappings) == "25-35"


# ---------------------------------------------------------------------------
# Hub normalisation
# ---------------------------------------------------------------------------

class TestNormaliseHub:
    def test_exact_match(self, hub_config):
        cfg = hub_config["hubs"]
        assert normalise_hub("outbox", cfg["mappings"], cfg["valid"]) == "Outbox"

    def test_case_insensitive(self, hub_config):
        cfg = hub_config["hubs"]
        assert normalise_hub("OUTBOX", cfg["mappings"], cfg["valid"]) == "Outbox"

    def test_full_name_mapping(self, hub_config):
        cfg = hub_config["hubs"]
        assert normalise_hub("stanbic business incubator", cfg["mappings"], cfg["valid"]) == "Sbil"

    def test_partial_match(self, hub_config):
        cfg = hub_config["hubs"]
        assert normalise_hub("Outbox Innovation Hub", cfg["mappings"], cfg["valid"]) == "Outbox"

    def test_none_returns_not_assigned(self, hub_config):
        cfg = hub_config["hubs"]
        assert normalise_hub(None, cfg["mappings"], cfg["valid"]) == "Not Assigned"

    def test_empty_returns_not_assigned(self, hub_config):
        cfg = hub_config["hubs"]
        assert normalise_hub("", cfg["mappings"], cfg["valid"]) == "Not Assigned"

    def test_unrecognised_returns_not_assigned(self, hub_config):
        cfg = hub_config["hubs"]
        assert normalise_hub("Random Hub XYZ", cfg["mappings"], cfg["valid"]) == "Not Assigned"


# ---------------------------------------------------------------------------
# Region assignment
# ---------------------------------------------------------------------------

class TestAssignRegion:
    def test_kampala_is_central(self, region_config):
        assert assign_region("Kampala", region_config["regions"]) == "Central"

    def test_mbale_is_eastern(self, region_config):
        assert assign_region("Mbale", region_config["regions"]) == "Eastern"

    def test_gulu_is_northern(self, region_config):
        assert assign_region("Gulu", region_config["regions"]) == "Northern"

    def test_mbarara_is_western(self, region_config):
        assert assign_region("Mbarara", region_config["regions"]) == "Western"

    def test_unknown_district_returns_unknown(self, region_config):
        assert assign_region("UnknownCity", region_config["regions"]) == "Unknown"

    def test_none_returns_unknown(self, region_config):
        assert assign_region(None, region_config["regions"]) == "Unknown"

    def test_case_insensitive(self, region_config):
        assert assign_region("kampala", region_config["regions"]) == "Central"


# ---------------------------------------------------------------------------
# Disability categorisation
# ---------------------------------------------------------------------------

class TestCategoriseDisability:
    def test_blind_is_visual(self, disability_config):
        cats = disability_config["disability"]["categories"]
        assert categorise_disability("I am blind", cats) == "Visual Impairment"

    def test_deaf_is_hearing(self, disability_config):
        cats = disability_config["disability"]["categories"]
        assert categorise_disability("deaf since birth", cats) == "Hearing Impairment"

    def test_wheelchair_is_physical(self, disability_config):
        cats = disability_config["disability"]["categories"]
        assert categorise_disability("uses a wheelchair", cats) == "Physical Disability"

    def test_none_is_not_disabled(self, disability_config):
        cats = disability_config["disability"]["categories"]
        assert categorise_disability("none", cats) == "Not Disabled"

    def test_null_is_not_disabled(self, disability_config):
        cats = disability_config["disability"]["categories"]
        assert categorise_disability(None, cats) == "Not Disabled"

    def test_empty_is_not_disabled(self, disability_config):
        cats = disability_config["disability"]["categories"]
        assert categorise_disability("", cats) == "Not Disabled"


# ---------------------------------------------------------------------------
# Quarter assignment
# ---------------------------------------------------------------------------

class TestAssignQuarter:
    def test_april_2026_is_y6q4(self, quarter_mapping):
        qm = quarter_mapping["quarter_mapping"]
        assert assign_quarter(pd.Timestamp("2026-04-10"), qm) == "Y6Q4"

    def test_january_2024_is_y4q3(self, quarter_mapping):
        qm = quarter_mapping["quarter_mapping"]
        assert assign_quarter(pd.Timestamp("2024-01-15"), qm) == "Y4Q3"

    def test_none_returns_none(self, quarter_mapping):
        qm = quarter_mapping["quarter_mapping"]
        assert assign_quarter(None, qm) is None

    def test_unmapped_date_returns_none(self, quarter_mapping):
        qm = quarter_mapping["quarter_mapping"]
        assert assign_quarter(pd.Timestamp("2019-01-01"), qm) is None

    def test_string_date_input(self, quarter_mapping):
        qm = quarter_mapping["quarter_mapping"]
        assert assign_quarter("2026-04-10", qm) == "Y6Q4"


# ---------------------------------------------------------------------------
# Email validation
# ---------------------------------------------------------------------------

class TestValidateEmail:
    def test_clean_email_is_valid(self, email_validation_config):
        cfg = email_validation_config["email_validation"]
        r = validate_email(
            "martin@gmail.com",
            cfg["disposable_domains"],
            cfg["domain_typos"],
            cfg["fake_keywords"],
            cfg["risk_score_threshold"],
        )
        assert r["status"] == "VALID"
        assert r["can_receive_emails"] is True
        assert r["likely_authentic"] is True

    def test_disposable_domain_flagged(self, email_validation_config):
        cfg = email_validation_config["email_validation"]
        r = validate_email(
            "user@mailinator.com",
            cfg["disposable_domains"],
            cfg["domain_typos"],
            cfg["fake_keywords"],
            cfg["risk_score_threshold"],
        )
        assert r["status"] in ("LIKELY_FAKE", "INVALID", "SUSPICIOUS")
        assert r["can_receive_emails"] is False

    def test_domain_typo_corrected(self, email_validation_config):
        cfg = email_validation_config["email_validation"]
        r = validate_email(
            "martin@gmial.com",
            cfg["disposable_domains"],
            cfg["domain_typos"],
            cfg["fake_keywords"],
            cfg["risk_score_threshold"],
        )
        assert r["corrected_email"] == "martin@gmail.com"
        assert "domain_typo_corrected" in r["flags"][0]

    def test_fake_keyword_flagged(self, email_validation_config):
        cfg = email_validation_config["email_validation"]
        r = validate_email(
            "test@gmail.com",
            cfg["disposable_domains"],
            cfg["domain_typos"],
            cfg["fake_keywords"],
            cfg["risk_score_threshold"],
        )
        assert any("fake_keyword" in f for f in r["flags"])

    def test_invalid_format_flagged(self, email_validation_config):
        cfg = email_validation_config["email_validation"]
        r = validate_email(
            "notanemail",
            cfg["disposable_domains"],
            cfg["domain_typos"],
            cfg["fake_keywords"],
            cfg["risk_score_threshold"],
        )
        assert r["status"] == "INVALID"

    def test_none_returns_invalid(self, email_validation_config):
        cfg = email_validation_config["email_validation"]
        r = validate_email(
            None,
            cfg["disposable_domains"],
            cfg["domain_typos"],
            cfg["fake_keywords"],
            cfg["risk_score_threshold"],
        )
        assert r["status"] == "INVALID"


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplicate:
    def test_removes_duplicates(self):
        df = pd.DataFrame({"email": ["a@b.com", "a@b.com", "c@d.com"]})
        result = deduplicate(df)
        assert len(result) == 2

    def test_keeps_first_occurrence(self):
        df = pd.DataFrame({
            "email": ["a@b.com", "a@b.com"],
            "name": ["Alice", "Alice2"],
        })
        result = deduplicate(df)
        assert result.iloc[0]["name"] == "Alice"

    def test_no_duplicates_unchanged(self):
        df = pd.DataFrame({"email": ["a@b.com", "c@d.com"]})
        result = deduplicate(df)
        assert len(result) == 2

    def test_empty_dataframe(self):
        df = pd.DataFrame({"email": []})
        result = deduplicate(df)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Merge conflict resolution
# ---------------------------------------------------------------------------

class TestResolveMergeConflicts:
    def test_fills_x_from_y_when_x_is_null(self):
        df = pd.DataFrame({
            "email": ["a@b.com"],
            "Gender_x": [None],
            "Gender_y": ["Male"],
        })
        result = resolve_merge_conflicts(df)
        assert "Gender" in result.columns
        assert result["Gender"].iloc[0] == "Male"

    def test_keeps_x_when_x_has_value(self):
        df = pd.DataFrame({
            "email": ["a@b.com"],
            "Gender_x": ["Female"],
            "Gender_y": ["Male"],
        })
        result = resolve_merge_conflicts(df)
        assert result["Gender"].iloc[0] == "Female"

    def test_drops_x_and_y_columns(self):
        df = pd.DataFrame({
            "email": ["a@b.com"],
            "Hub_x": ["Outbox"],
            "Hub_y": ["Miic"],
        })
        result = resolve_merge_conflicts(df)
        assert "Hub_x" not in result.columns
        assert "Hub_y" not in result.columns
        assert "Hub" in result.columns

    def test_no_conflicts_unchanged(self):
        df = pd.DataFrame({"email": ["a@b.com"], "Gender": ["Female"]})
        result = resolve_merge_conflicts(df)
        assert list(result.columns) == ["email", "Gender"]


# ---------------------------------------------------------------------------
# Full name building
# ---------------------------------------------------------------------------

class TestBuildFullName:
    def test_builds_full_name(self):
        df = pd.DataFrame({
            "First Name": ["Alice"],
            "Last Name": ["Nakamya"],
        })
        result = build_full_name(df)
        assert result["Full Name"].iloc[0] == "Alice Nakamya"

    def test_skips_if_full_name_exists(self):
        df = pd.DataFrame({
            "First Name": ["Alice"],
            "Last Name": ["Nakamya"],
            "Full Name": ["Alice N"],
        })
        result = build_full_name(df)
        assert result["Full Name"].iloc[0] == "Alice N"

    def test_handles_missing_first_name(self):
        df = pd.DataFrame({
            "First Name": [None],
            "Last Name": ["Nakamya"],
        })
        result = build_full_name(df)
        assert result["Full Name"].iloc[0] == "Nakamya"
