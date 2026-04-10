"""
ingest.py — File discovery and loading

Responsibilities:
- Find the latest version of each source file in the course raw data folder
- Load files into pandas DataFrames
- Normalise the email column name to 'email'
- Abstract the source (file vs API) behind a common interface

When Thinkific API access is available, swap FileIngester for ThinkificIngester.
Both return the same dict of DataFrames — everything downstream is unaffected.
"""

import glob
import logging
import os
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _latest_file(folder: str, pattern: str) -> str | None:
    """Return the most recently modified file matching pattern in folder."""
    matches = glob.glob(os.path.join(folder, pattern))
    if not matches:
        return None
    return max(matches, key=os.path.getmtime)


def _load_file(filepath: str) -> pd.DataFrame:
    """Load a CSV or Excel file into a DataFrame."""
    ext = Path(filepath).suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(filepath, low_memory=False)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath)
    else:
        raise ValueError(f"Unsupported file type: {ext} — {filepath}")
    logger.info(f"Loaded {len(df)} rows from {Path(filepath).name}")
    return df


def _normalise_email_column(df: pd.DataFrame, email_columns: list[str]) -> pd.DataFrame:
    """Rename any known email column variant to 'email'."""
    for col in email_columns:
        if col in df.columns and col != "email":
            df = df.rename(columns={col: "email"})
            logger.info(f"Renamed column '{col}' → 'email'")
            break
    if "email" not in df.columns:
        logger.warning("No email column found in DataFrame")
    return df


# ---------------------------------------------------------------------------
# File-based ingester (current mode)
# ---------------------------------------------------------------------------

class FileIngester:
    """
    Discovers and loads Thinkific export files from a local folder.

    Usage:
        ingester = FileIngester(course_config, base_config)
        data = ingester.load()
        # data = {
        #     "post_course": DataFrame,
        #     "pre_course": DataFrame | None,
        #     "progress": DataFrame,
        #     "user_export": DataFrame,
        #     "master_reference": DataFrame | None,
        # }
    """

    def __init__(self, course_config: dict, base_config: dict):
        self.course_config = course_config
        self.base_config = base_config
        self.folder = course_config["raw_data_folder"]
        self.email_columns = base_config["email_columns"]

    def _load_source(self, pattern: str, label: str) -> pd.DataFrame | None:
        filepath = _latest_file(self.folder, pattern)
        if not filepath:
            logger.warning(f"No file found for '{label}' with pattern: {pattern}")
            return None
        df = _load_file(filepath)
        df = _normalise_email_column(df, self.email_columns)
        return df

    def load(self) -> dict[str, pd.DataFrame | None]:
        source_files = self.course_config.get("source_files", {})
        common_files = self.base_config.get("common_files", {})
        has_pre_course = self.course_config.get("has_pre_course", True)

        data = {}

        # Post-course assessment (always present)
        data["post_course"] = self._load_source(
            source_files["post_course_assessment"],
            "post_course_assessment"
        )

        # Pre-course assessment (optional — FL 4 Artisans has none)
        if has_pre_course and "pre_course_assessment" in source_files:
            data["pre_course"] = self._load_source(
                source_files["pre_course_assessment"],
                "pre_course_assessment"
            )
        else:
            data["pre_course"] = None
            logger.info("Pre-course assessment skipped (not configured for this course)")

        # Progress tracking (common to all courses)
        data["progress"] = self._load_source(
            common_files["progress"],
            "progress"
        )

        # User export (common to all courses)
        data["user_export"] = self._load_source(
            common_files["user_export"],
            "user_export"
        )

        # Academy-specific sources
        if "enrollments" in source_files:
            data["enrollments"] = self._load_source(
                source_files["enrollments"],
                "enrollments"
            )
        if "individual_profiling" in source_files:
            data["individual_profiling"] = self._load_source(
                source_files["individual_profiling"],
                "individual_profiling"
            )
        if "business_profiling" in source_files:
            data["business_profiling"] = self._load_source(
                source_files["business_profiling"],
                "business_profiling"
            )

        # Master reference file (BFC or course-specific)
        master_ref = self.course_config.get("master_reference_file")
        if master_ref and os.path.exists(master_ref):
            data["master_reference"] = _load_file(master_ref)
            data["master_reference"] = _normalise_email_column(
                data["master_reference"], self.email_columns
            )
        else:
            data["master_reference"] = None
            if master_ref:
                logger.warning(f"Master reference file not found: {master_ref}")

        # Log summary
        loaded = [k for k, v in data.items() if v is not None]
        skipped = [k for k, v in data.items() if v is None]
        logger.info(f"Ingestion complete — loaded: {loaded}")
        if skipped:
            logger.info(f"Skipped (not found or not applicable): {skipped}")

        return data


# ---------------------------------------------------------------------------
# API ingester (placeholder — ready for when Thinkific grants API access)
# ---------------------------------------------------------------------------

class ThinkificIngester:
    """
    Fetches Thinkific course data via REST API.

    Drop-in replacement for FileIngester — returns the same dict structure.
    Activate by setting ingestion.mode: api in base.yaml.
    """

    def __init__(self, course_config: dict, base_config: dict):
        self.course_config = course_config
        self.base_config = base_config
        self.api_key = base_config["ingestion"].get("api_key", "")
        self.base_url = base_config["ingestion"].get("api_base_url", "")

    def load(self) -> dict[str, pd.DataFrame | None]:
        # TODO: implement when Thinkific API access is granted
        # Endpoints to call:
        #   GET /api/v2/courses/{course_id}/enrollments
        #   GET /api/v2/courses/{course_id}/users
        #   GET /api/v2/courses/{course_id}/lesson_completions
        raise NotImplementedError(
            "ThinkificIngester is not yet implemented. "
            "Set ingestion.mode: file in base.yaml to use file-based ingestion."
        )


# ---------------------------------------------------------------------------
# Factory — returns the right ingester based on config
# ---------------------------------------------------------------------------

def get_ingester(course_config: dict, base_config: dict) -> FileIngester | ThinkificIngester:
    """
    Return the correct ingester based on ingestion.mode in base config.

    When API access is granted:
    1. Set ingestion.mode: api in config/base.yaml
    2. Set ingestion.api_key and ingestion.api_base_url
    3. Implement ThinkificIngester.load()
    4. Nothing else in the pipeline changes.
    """
    mode = base_config.get("ingestion", {}).get("mode", "file")
    if mode == "api":
        logger.info("Using ThinkificIngester (API mode)")
        return ThinkificIngester(course_config, base_config)
    logger.info("Using FileIngester (file mode)")
    return FileIngester(course_config, base_config)
