"""
course_flow.py — Parametrized Prefect flow for a single course

This flow runs the full pipeline for one course:
  1. Ingest   — discover and load source files
  2. Validate — check schemas before cleaning
  3. Merge    — join all sources on email
  4. Clean    — apply all cleaning functions
  5. Quality  — assert output meets quality standards
  6. Export   — write to DuckDB + file

Pass any course config to run_course_flow() and it handles the rest.
Academy runs through run_academy_flow() which has additional merge logic
and writes the master BFC reference file before other courses can run.
"""

import logging
import os

import pandas as pd
import yaml
from prefect import flow, task, get_run_logger

from src.clean import clean_dataframe
from src.export import export
from src.ingest import get_ingester
from src.quality import run_quality_checks
from src.validate import validate_all


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_configs(course_key: str, config_dir: str = "config") -> tuple[dict, dict]:
    """Load base config and course-specific config, merging where needed."""
    with open(os.path.join(config_dir, "base.yaml"), encoding="utf-8") as f:
        base_config = yaml.safe_load(f)
    with open(os.path.join(config_dir, f"{course_key}.yaml"), encoding="utf-8") as f:
        course_config = yaml.safe_load(f)
    return base_config, course_config


# ---------------------------------------------------------------------------
# Prefect tasks — each step is a task so Prefect tracks it individually
# ---------------------------------------------------------------------------

@task(name="ingest", retries=1)
def task_ingest(course_config: dict, base_config: dict) -> dict:
    logger = get_run_logger()
    logger.info(f"Ingesting data for: {course_config['course_name']}")
    ingester = get_ingester(course_config, base_config)
    data = ingester.load()
    loaded = [k for k, v in data.items() if v is not None]
    logger.info(f"Loaded sources: {loaded}")
    return data


@task(name="validate")
def task_validate(
    data: dict, course_config: dict, base_config: dict
) -> dict:
    logger = get_run_logger()
    logger.info(f"Validating sources for: {course_config['course_name']}")
    validate_all(data, course_config, base_config)
    logger.info("Validation passed")
    return data


@task(name="merge")
def task_merge(data: dict, course_config: dict, base_config: dict) -> pd.DataFrame:
    """
    Merge all loaded sources into a single DataFrame.

    Merge order:
      1. Start with progress (has % Completed — the primary metric)
      2. Left join post_course assessment (adds survey responses: gender, hub, age)
      3. Left join pre_course assessment if present
      4. Left join user_export (adds phone number)
      5. Left join master_reference (BFC — enriches with profiling data)
    """
    logger = get_run_logger()
    join_key = base_config.get("join_key", "email")

    progress = data.get("progress")
    post_course = data.get("post_course")
    pre_course = data.get("pre_course")
    user_export = data.get("user_export")
    master_ref = data.get("master_reference")

    # Academy has its own sources — handled in run_academy_flow
    individual = data.get("individual_profiling")
    business = data.get("business_profiling")
    enrollments = data.get("enrollments")

    if progress is None and post_course is None:
        raise ValueError("Cannot merge — both progress and post_course are None")

    # Start with progress as base (it has every enrolled participant)
    if progress is not None:
        df = progress.copy()
    else:
        df = post_course.copy()
        post_course = None

    # Merge post_course survey responses
    if post_course is not None:
        # Only keep the survey response columns + email to avoid column explosion
        response_mapping = course_config.get("survey_response_mapping", {})
        response_cols = [v for v in response_mapping.values() if v is not None]
        keep_cols = [join_key] + [c for c in response_cols if c in post_course.columns]
        df = df.merge(post_course[keep_cols], on=join_key, how="left", suffixes=("", "_post"))
        logger.info(f"Merged post_course: {len(df)} rows")

    # Merge pre_course if present
    if pre_course is not None:
        response_cols_pre = [
            c for c in pre_course.columns
            if c.startswith("Response") or c == join_key
        ]
        df = df.merge(
            pre_course[[join_key] + [c for c in response_cols_pre if c != join_key]],
            on=join_key, how="left", suffixes=("", "_pre")
        )
        logger.info(f"Merged pre_course: {len(df)} rows")

    # Merge user_export for phone numbers
    if user_export is not None:
        phone_cols = [join_key] + [
            c for c in user_export.columns
            if any(kw in c.lower() for kw in ("phone", "mobile", "tel"))
            and c != join_key
        ]
        if len(phone_cols) > 1:
            df = df.merge(user_export[phone_cols], on=join_key, how="left", suffixes=("", "_usr"))
            logger.info(f"Merged user_export (phone): {len(df)} rows")

    # Merge master BFC reference for profiling data
    if master_ref is not None:
        df = df.merge(master_ref, on=join_key, how="left", suffixes=("_x", "_y"))
        logger.info(f"Merged master_reference: {len(df)} rows")

    # Academy-specific: merge individual profiling and business profiling
    if individual is not None:
        df = df.merge(individual, on=join_key, how="left", suffixes=("_x", "_y"))
        logger.info(f"Merged individual_profiling: {len(df)} rows")
    if business is not None:
        df = df.merge(business, on=join_key, how="left", suffixes=("_x", "_y"))
        logger.info(f"Merged business_profiling: {len(df)} rows")
    if enrollments is not None:
        df = df.merge(enrollments, on=join_key, how="left", suffixes=("_x", "_y"))
        logger.info(f"Merged enrollments: {len(df)} rows")

    # Rename survey response columns using course config mapping
    response_mapping = course_config.get("survey_response_mapping", {})
    rename_map = {}
    for field_name, response_col in response_mapping.items():
        if response_col and response_col in df.columns:
            friendly_names = {
                "gender": "Gender",
                "age_group": "Age group",
                "hub": "ESO Hub",
                "district": "District",
            }
            if field_name in friendly_names:
                rename_map[response_col] = friendly_names[field_name]
    if rename_map:
        df = df.rename(columns=rename_map)
        logger.info(f"Renamed survey columns: {rename_map}")

    logger.info(f"Merge complete: {len(df)} rows, {len(df.columns)} columns")
    return df


@task(name="clean")
def task_clean(
    df: pd.DataFrame, course_config: dict, base_config: dict
) -> pd.DataFrame:
    logger = get_run_logger()
    logger.info(f"Cleaning: {course_config['course_name']} — {len(df)} rows in")
    df_clean = clean_dataframe(df, base_config, course_config)
    logger.info(f"Cleaning complete: {len(df_clean)} rows out")
    return df_clean


@task(name="quality_check")
def task_quality(
    df_input: pd.DataFrame,
    df_output: pd.DataFrame,
    course_config: dict,
    base_config: dict,
    reports_dir: str,
) -> None:
    logger = get_run_logger()
    logger.info(f"Running quality checks: {course_config['course_name']}")
    report = run_quality_checks(df_input, df_output, course_config, base_config, reports_dir)
    logger.info(
        f"Quality checks passed: {len(report.checks)} checks, "
        f"{len(report.warnings)} warning(s)"
    )


@task(name="export")
def task_export(
    df: pd.DataFrame, course_config: dict, base_config: dict
) -> dict:
    logger = get_run_logger()
    logger.info(f"Exporting: {course_config['course_name']}")
    outputs = export(df, course_config, base_config)
    for dest, path in outputs.items():
        logger.info(f"  → {dest}: {path}")
    return outputs


# ---------------------------------------------------------------------------
# Course flow
# ---------------------------------------------------------------------------

@flow(name="course-pipeline", log_prints=True)
def run_course_flow(
    course_key: str,
    config_dir: str = "config",
) -> dict:
    """
    Run the full pipeline for a single course.

    Args:
        course_key:  One of: compliance, career_planning, e_biz,
                     fl4_artisans, omusomo
        config_dir:  Path to config directory (default: config/)

    Returns:
        dict of output paths (duckdb, file)

    Usage:
        from flows.course_flow import run_course_flow
        run_course_flow(course_key="compliance")
    """
    logger = get_run_logger()
    logger.info(f"Starting pipeline for course: {course_key}")

    base_config, course_config = load_configs(course_key, config_dir)
    reports_dir = base_config["paths"]["reports"]

    data = task_ingest(course_config, base_config)
    data = task_validate(data, course_config, base_config)
    df_merged = task_merge(data, course_config, base_config)
    df_clean = task_clean(df_merged, course_config, base_config)
    task_quality(df_merged, df_clean, course_config, base_config, reports_dir)
    outputs = task_export(df_clean, course_config, base_config)

    logger.info(f"Pipeline complete for: {course_config['course_name']}")
    return outputs


# ---------------------------------------------------------------------------
# Academy flow (runs first — produces master BFC file)
# ---------------------------------------------------------------------------

@flow(name="academy-pipeline", log_prints=True)
def run_academy_flow(config_dir: str = "config") -> dict:
    """
    Run the Academy (BFC master) pipeline.

    Must run before any other course flows because it produces
    final_cleaned_bfc.xlsx which the other courses depend on.

    Returns:
        dict of output paths
    """
    logger = get_run_logger()
    logger.info("Starting Academy master pipeline")

    base_config, course_config = load_configs("academy", config_dir)
    reports_dir = base_config["paths"]["reports"]

    data = task_ingest(course_config, base_config)
    data = task_validate(data, course_config, base_config)
    df_merged = task_merge(data, course_config, base_config)
    df_clean = task_clean(df_merged, course_config, base_config)
    task_quality(df_merged, df_clean, course_config, base_config, reports_dir)
    outputs = task_export(df_clean, course_config, base_config)

    logger.info(f"Academy pipeline complete — master BFC written to: {outputs.get('file')}")
    return outputs
