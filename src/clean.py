"""
clean.py — All data cleaning functions

Responsibilities:
- Clean and standardise every field in the merged DataFrame
- Read all mappings and rules from config (nothing hardcoded here)
- Each function is independent and testable in isolation
- Course-specific behaviour is handled via config parameters passed in

Functions are organised in the order they run in the pipeline:
  1. Email cleaning
  2. Name building
  3. Date and age cleaning
  4. Gender normalisation
  5. Age group normalisation
  6. Hub normalisation
  7. Region assignment
  8. Disability categorisation
  9. Nationality filling
  10. Quarter assignment
  11. Completion categorisation
  12. Email validation (optional — controlled by course config)
  13. Deduplication
  14. Merge conflict resolution (_x / _y columns)
  15. Master orchestrator — clean_dataframe()
"""

import logging
import re
from datetime import date, datetime

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Email cleaning
# ---------------------------------------------------------------------------

def clean_email(email: str | None) -> str | None:
    """Strip whitespace and lowercase an email address."""
    if pd.isna(email) or not isinstance(email, str):
        return None
    cleaned = email.strip().lower()
    return cleaned if cleaned else None


def clean_email_column(df: pd.DataFrame) -> pd.DataFrame:
    """Apply clean_email to the email column."""
    if "email" not in df.columns:
        logger.warning("clean_email_column: no 'email' column found — skipping")
        return df
    before_nulls = df["email"].isna().sum()
    df["email"] = df["email"].apply(clean_email)
    after_nulls = df["email"].isna().sum()
    new_nulls = after_nulls - before_nulls
    if new_nulls > 0:
        logger.warning(f"clean_email_column: {new_nulls} email(s) became null after cleaning")
    logger.info(f"clean_email_column: cleaned {len(df)} emails")
    return df


# ---------------------------------------------------------------------------
# 2. Name building
# ---------------------------------------------------------------------------

def build_full_name(df: pd.DataFrame) -> pd.DataFrame:
    """Concatenate First Name + Last Name into Full Name if not already present."""
    first_col = next((c for c in df.columns if c.lower() in ("first name", "firstname")), None)
    last_col = next((c for c in df.columns if c.lower() in ("last name", "lastname")), None)

    if "Full Name" not in df.columns and first_col and last_col:
        df["Full Name"] = (
            df[first_col].fillna("").str.strip()
            + " "
            + df[last_col].fillna("").str.strip()
        ).str.strip()
        logger.info("build_full_name: Full Name column created")
    return df


# ---------------------------------------------------------------------------
# 3. Date and age cleaning
# ---------------------------------------------------------------------------

DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
    "%Y/%m/%d",
]


def clean_date(value: str | None) -> date | None:
    """
    Parse a date string trying multiple formats.
    Returns a date object or None if unparseable.
    """
    if pd.isna(value) or not isinstance(value, str):
        return None
    value = value.strip()

    # Try pandas first (handles ISO and many common formats)
    try:
        parsed = pd.to_datetime(value, infer_datetime_format=True, errors="raise")
        return parsed.date()
    except Exception:
        pass

    # Try explicit formats
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    logger.warning(f"clean_date: could not parse date value '{value}'")
    return None


def calculate_age(dob: date | None, reference_date: date | None = None) -> int | None:
    """Calculate age in years from date of birth."""
    if dob is None:
        return None
    ref = reference_date or date.today()
    try:
        age = ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))
        return age if 0 <= age <= 120 else None
    except Exception:
        return None


def clean_date_column(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Parse a date column and add a cleaned version."""
    if column not in df.columns:
        return df
    df[column] = df[column].apply(
        lambda v: clean_date(str(v)) if not pd.isna(v) else None
    )
    return df


def add_age_column(df: pd.DataFrame, dob_column: str = "DOB") -> pd.DataFrame:
    """Add an Age column calculated from the DOB column."""
    if dob_column not in df.columns:
        return df
    df["Age"] = df[dob_column].apply(calculate_age)
    logger.info(f"add_age_column: calculated age from '{dob_column}'")
    return df


# ---------------------------------------------------------------------------
# 4. Gender normalisation
# ---------------------------------------------------------------------------

def normalise_gender(
    value: str | None,
    mappings: dict,
    valid_values: list[str],
) -> str:
    """Normalise a raw gender string to a standard value."""
    if pd.isna(value) or not isinstance(value, str):
        return "Not Specified"
    key = value.strip().lower()
    if key in mappings:
        return mappings[key]
    # Check if it's already a valid value (case-insensitive)
    for valid in valid_values:
        if key == valid.lower():
            return valid
    return "Not Specified"


def normalise_gender_column(
    df: pd.DataFrame,
    config: dict,
    extra_mappings: dict | None = None,
) -> pd.DataFrame:
    """Apply gender normalisation to the Gender column."""
    col = next((c for c in df.columns if c.lower() == "gender"), None)
    if not col:
        logger.warning("normalise_gender_column: no Gender column found — skipping")
        return df

    mappings = dict(config["gender"]["mappings"])
    if extra_mappings:
        mappings.update({k.lower(): v for k, v in extra_mappings.items()})

    valid_values = config["gender"]["valid_values"]
    df["Gender"] = df[col].apply(
        lambda v: normalise_gender(v, mappings, valid_values)
    )
    if col != "Gender":
        df = df.drop(columns=[col])
    logger.info("normalise_gender_column: Gender column normalised")
    return df


# ---------------------------------------------------------------------------
# 5. Age group normalisation
# ---------------------------------------------------------------------------

def normalise_age_group(
    value: str | None,
    mappings: dict,
) -> str:
    """Normalise a raw age group string to a standard label."""
    if pd.isna(value) or not isinstance(value, str):
        return "Not Assigned"
    key = value.strip().lower()
    if key in mappings:
        return mappings[key]
    # Already a valid standard label
    standard = ["Below 18", "18-24", "25-35", "36+", "Not Assigned"]
    for s in standard:
        if key == s.lower():
            return s
    return "Not Assigned"


def normalise_age_group_column(
    df: pd.DataFrame,
    config: dict,
    extra_mappings: dict | None = None,
) -> pd.DataFrame:
    """Apply age group normalisation to the Age group column."""
    col = next((c for c in df.columns if c.lower() in ("age group", "age_group")), None)
    if not col:
        logger.warning("normalise_age_group_column: no Age group column found — skipping")
        return df

    mappings = dict(config["age_bins"]["mappings"])
    if extra_mappings:
        mappings.update({k.lower(): v for k, v in extra_mappings.items()})

    df["Age group"] = df[col].apply(lambda v: normalise_age_group(v, mappings))
    if col != "Age group":
        df = df.drop(columns=[col])
    logger.info("normalise_age_group_column: Age group column normalised")
    return df


# ---------------------------------------------------------------------------
# 6. Hub normalisation
# ---------------------------------------------------------------------------

def normalise_hub(
    value: str | None,
    mappings: dict,
    valid_hubs: list[str],
) -> str:
    """Normalise a raw ESO Hub string to a standard hub name."""
    if pd.isna(value) or not isinstance(value, str):
        return "Not Assigned"
    key = value.strip().lower()
    if key in mappings:
        return mappings[key]
    # Check if it's already a valid hub (case-insensitive)
    for hub in valid_hubs:
        if key == hub.lower():
            return hub
    # Partial match — value contains a known hub name
    for hub in valid_hubs:
        if hub.lower() in key:
            return hub
    logger.warning(f"normalise_hub: unrecognised hub value '{value}' — set to Not Assigned")
    return "Not Assigned"


def normalise_hub_column(
    df: pd.DataFrame,
    config: dict,
    extra_mappings: dict | None = None,
) -> pd.DataFrame:
    """Apply hub normalisation to the ESO Hub column."""
    col = next(
        (c for c in df.columns if c.lower() in ("eso hub", "hub", "eso_hub")), None
    )
    if not col:
        logger.warning("normalise_hub_column: no Hub column found — skipping")
        return df

    mappings = dict(config["hubs"]["mappings"])
    if extra_mappings:
        mappings.update({k.lower(): v for k, v in extra_mappings.items()})

    valid_hubs = config["hubs"]["valid"]
    df["ESO Hub"] = df[col].apply(
        lambda v: normalise_hub(v, mappings, valid_hubs)
    )
    if col != "ESO Hub":
        df = df.drop(columns=[col])
    logger.info("normalise_hub_column: ESO Hub column normalised")
    return df


# ---------------------------------------------------------------------------
# 7. Region assignment
# ---------------------------------------------------------------------------

def assign_region(district: str | None, region_map: dict) -> str:
    """Map a district name to its region."""
    if pd.isna(district) or not isinstance(district, str):
        return "Unknown"
    district_clean = district.strip()
    for region, districts in region_map.items():
        if district_clean in districts:
            return region
    # Case-insensitive fallback
    district_lower = district_clean.lower()
    for region, districts in region_map.items():
        if any(district_lower == d.lower() for d in districts):
            return region
    return "Unknown"


def assign_region_column(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Add a Region column based on the District column."""
    col = next((c for c in df.columns if c.lower() == "district"), None)
    if not col:
        logger.info("assign_region_column: no District column — skipping region assignment")
        return df
    region_map = config["regions"]
    df["Region"] = df[col].apply(lambda v: assign_region(v, region_map))
    logger.info("assign_region_column: Region column assigned")
    return df


# ---------------------------------------------------------------------------
# 8. Disability categorisation
# ---------------------------------------------------------------------------

def categorise_disability(value: str | None, categories: dict) -> str:
    """Categorise a free-text disability response into a standard category."""
    if pd.isna(value) or not isinstance(value, str) or value.strip() == "":
        return "Not Disabled"
    value_lower = value.strip().lower()
    for category, keywords in categories.items():
        if any(kw.lower() in value_lower for kw in keywords if kw):
            return category
    return "Not Disabled"


def categorise_disability_column(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Apply disability categorisation to the DISABILITY column."""
    col = next((c for c in df.columns if c.lower() in ("disability", "pwd")), None)
    if not col:
        logger.warning("categorise_disability_column: no Disability column found — skipping")
        return df
    categories = config["disability"]["categories"]
    df["DISABILITY"] = df[col].apply(lambda v: categorise_disability(v, categories))
    if col != "DISABILITY":
        df = df.drop(columns=[col])
    logger.info("categorise_disability_column: DISABILITY column categorised")
    return df


# ---------------------------------------------------------------------------
# 9. Nationality filling
# ---------------------------------------------------------------------------

def fill_nationality(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Fill missing NATIONALITY values with the configured default."""
    col = next((c for c in df.columns if c.lower() == "nationality"), None)
    default = config.get("nationality", {}).get("default", "National")
    if col:
        df["NATIONALITY"] = df[col].fillna(default).replace("", default)
        if col != "NATIONALITY":
            df = df.drop(columns=[col])
    else:
        df["NATIONALITY"] = default
    logger.info(f"fill_nationality: NATIONALITY filled with default '{default}'")
    return df


# ---------------------------------------------------------------------------
# 10. Quarter assignment
# ---------------------------------------------------------------------------

def assign_quarter(date_value, quarter_mapping: dict) -> str | None:
    """Map a date to a programme quarter label (e.g. Y6Q4)."""
    if pd.isna(date_value):
        return None
    try:
        if isinstance(date_value, str):
            date_value = pd.to_datetime(date_value, errors="coerce")
        if pd.isna(date_value):
            return None
        key = date_value.strftime("%Y-%m")
        return quarter_mapping.get(key)
    except Exception:
        return None


def assign_quarter_column(
    df: pd.DataFrame,
    config: dict,
    date_column: str = "Completed At",
) -> pd.DataFrame:
    """Add a Quarter column based on the completion date."""
    if date_column not in df.columns:
        logger.warning(f"assign_quarter_column: '{date_column}' not found — skipping")
        return df
    quarter_mapping = config.get("quarter_mapping", {})
    df["Quarter"] = df[date_column].apply(
        lambda v: assign_quarter(v, quarter_mapping)
    )
    logger.info(f"assign_quarter_column: Quarter assigned from '{date_column}'")
    return df


# ---------------------------------------------------------------------------
# 11. Completion categorisation
# ---------------------------------------------------------------------------

def categorise_completion(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Bin the % Completed column into completion categories."""
    col = next(
        (c for c in df.columns if "completed" in c.lower() and "%" in c), None
    )
    if not col:
        col = next((c for c in df.columns if c.lower() == "% completed"), None)
    if not col:
        logger.warning("categorise_completion: no '% Completed' column found — skipping")
        return df

    bins = config["completion_bins"]["boundaries"]
    labels = config["completion_bins"]["labels"]
    df["% Completed Category"] = pd.cut(
        pd.to_numeric(df[col], errors="coerce"),
        bins=bins,
        labels=labels,
        include_lowest=True,
    )
    logger.info("categorise_completion: % Completed Category column created")
    return df


# ---------------------------------------------------------------------------
# 12. Email validation
# ---------------------------------------------------------------------------

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def validate_email(
    email: str | None,
    disposable_domains: list[str],
    domain_typos: dict,
    fake_keywords: list[str],
    risk_threshold: int = 5,
) -> dict:
    """
    Validate a single email address.
    Returns a dict with keys: status, risk_score, corrected_email, flags
    Status values: VALID | NEEDS_REVIEW | SUSPICIOUS | LIKELY_FAKE | INVALID
    """
    result = {
        "status": "INVALID",
        "risk_score": 0,
        "corrected_email": email,
        "flags": [],
        "can_receive_emails": False,
        "likely_authentic": False,
    }

    if not email or not isinstance(email, str):
        result["flags"].append("null_or_empty")
        return result

    email = email.strip().lower()

    # Format check
    if not EMAIL_REGEX.match(email):
        result["flags"].append("invalid_format")
        result["risk_score"] += 10
        return result

    domain = email.split("@")[-1]

    # Domain typo correction
    if domain in domain_typos:
        corrected_domain = domain_typos[domain]
        result["corrected_email"] = email.replace(domain, corrected_domain)
        result["flags"].append(f"domain_typo_corrected:{domain}->{corrected_domain}")
        result["risk_score"] += 1

    # Disposable domain check
    if domain in disposable_domains:
        result["flags"].append("disposable_domain")
        result["risk_score"] += 8

    # Fake keyword check
    local_part = email.split("@")[0]
    for keyword in fake_keywords:
        if keyword in local_part:
            result["flags"].append(f"fake_keyword:{keyword}")
            result["risk_score"] += 4
            break

    # Keyboard pattern detection (e.g. asdf, qwerty, 1234)
    keyboard_patterns = ["qwerty", "asdfgh", "zxcvbn", "123456", "abcdef"]
    if any(p in local_part for p in keyboard_patterns):
        result["flags"].append("keyboard_pattern")
        result["risk_score"] += 3

    # Sequential numbers (e.g. user1, user2, user3 — bulk registration)
    if re.search(r"\d{3,}$", local_part):
        result["flags"].append("sequential_numbers")
        result["risk_score"] += 2

    # Determine status from risk score
    score = result["risk_score"]
    if score == 0:
        result["status"] = "VALID"
        result["can_receive_emails"] = True
        result["likely_authentic"] = True
    elif score <= 2:
        result["status"] = "NEEDS_REVIEW"
        result["can_receive_emails"] = True
        result["likely_authentic"] = True
    elif score <= risk_threshold:
        result["status"] = "SUSPICIOUS"
        result["can_receive_emails"] = False
        result["likely_authentic"] = False
    elif score <= 8:
        result["status"] = "LIKELY_FAKE"
        result["can_receive_emails"] = False
        result["likely_authentic"] = False
    else:
        result["status"] = "INVALID"
        result["can_receive_emails"] = False
        result["likely_authentic"] = False

    return result


def validate_email_column(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """
    Apply email validation to the email column.
    Adds: email_status, email_risk_score, corrected_email,
          can_receive_emails, likely_authentic columns.
    """
    if "email" not in df.columns:
        logger.warning("validate_email_column: no email column — skipping")
        return df

    ev_config = config.get("email_validation", {})
    disposable_domains = ev_config.get("disposable_domains", [])
    domain_typos = ev_config.get("domain_typos", {})
    fake_keywords = ev_config.get("fake_keywords", [])
    risk_threshold = ev_config.get("risk_score_threshold", 5)

    results = df["email"].apply(
        lambda e: validate_email(e, disposable_domains, domain_typos, fake_keywords, risk_threshold)
    )

    df["email_status"] = results.apply(lambda r: r["status"])
    df["email_risk_score"] = results.apply(lambda r: r["risk_score"])
    df["corrected_email"] = results.apply(lambda r: r["corrected_email"])
    df["can_receive_emails"] = results.apply(lambda r: r["can_receive_emails"])
    df["likely_authentic"] = results.apply(lambda r: r["likely_authentic"])

    valid_count = (df["email_status"] == "VALID").sum()
    flagged_count = len(df) - valid_count
    logger.info(
        f"validate_email_column: {valid_count} valid, {flagged_count} flagged "
        f"out of {len(df)} emails"
    )
    return df


# ---------------------------------------------------------------------------
# 13. Deduplication
# ---------------------------------------------------------------------------

def deduplicate(df: pd.DataFrame, join_key: str = "email") -> pd.DataFrame:
    """Remove duplicate rows keeping the first occurrence per join key."""
    before = len(df)
    df = df.drop_duplicates(subset=join_key, keep="first")
    removed = before - len(df)
    if removed > 0:
        logger.info(f"deduplicate: removed {removed} duplicate(s) on '{join_key}'")
    return df


# ---------------------------------------------------------------------------
# 14. Merge conflict resolution (_x / _y columns)
# ---------------------------------------------------------------------------

def resolve_merge_conflicts(df: pd.DataFrame) -> pd.DataFrame:
    """
    After a left merge, pandas creates _x and _y suffixed columns when
    both DataFrames share column names beyond the join key.

    Strategy: fill _x from _y where _x is null, then drop _y.
    This keeps the primary source value where it exists, and fills
    gaps from the reference source.
    """
    x_cols = [c for c in df.columns if c.endswith("_x")]
    for col_x in x_cols:
        base = col_x[:-2]
        col_y = base + "_y"
        if col_y in df.columns:
            df[base] = df[col_x].fillna(df[col_y])
            df = df.drop(columns=[col_x, col_y])
            logger.info(f"resolve_merge_conflicts: resolved '{base}' from _x/_y columns")
    return df


# ---------------------------------------------------------------------------
# 15. Master orchestrator
# ---------------------------------------------------------------------------

def clean_dataframe(
    df: pd.DataFrame,
    base_config: dict,
    course_config: dict,
) -> pd.DataFrame:
    """
    Run the full cleaning pipeline on a merged DataFrame.

    Order:
      1.  Resolve _x/_y merge conflicts
      2.  Clean email
      3.  Build full name
      4.  Normalise gender (+ course-specific extra mappings)
      5.  Normalise age group (+ course-specific extra mappings)
      6.  Normalise hub (+ course-specific extra mappings)
      7.  Assign region
      8.  Categorise disability
      9.  Fill nationality
      10. Assign quarter
      11. Categorise completion
      12. Email validation (if enabled for this course)
      13. Deduplicate
    """
    course_name = course_config.get("course_name", "Unknown")
    logger.info(f"clean_dataframe: starting clean for '{course_name}' — {len(df)} rows")

    df = resolve_merge_conflicts(df)
    df = clean_email_column(df)
    df = build_full_name(df)
    df = normalise_gender_column(
        df, base_config,
        extra_mappings=course_config.get("extra_gender_mappings")
    )
    df = normalise_age_group_column(
        df, base_config,
        extra_mappings=course_config.get("extra_age_mappings")
    )
    df = normalise_hub_column(
        df, base_config,
        extra_mappings=course_config.get("extra_hub_mappings")
    )
    df = assign_region_column(df, base_config)
    df = categorise_disability_column(df, base_config)
    df = fill_nationality(df, base_config)
    df = assign_quarter_column(df, base_config)
    df = categorise_completion(df, base_config)

    if course_config.get("email_validation_enabled", False):
        df = validate_email_column(df, base_config)

    df = deduplicate(df)

    logger.info(f"clean_dataframe: cleaning complete — {len(df)} rows remaining")
    return df
