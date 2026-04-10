"""
run.py — Direct pipeline runner (no Prefect server required)

Use this to run the pipeline locally without needing Prefect infrastructure.
Prefect flows are still used for structure and logging, but run in-process.

Usage:
    python run.py                     # run all 6 courses
    python run.py compliance          # run one course only
    python run.py academy             # run Academy master only
"""

import logging
import sys
from datetime import datetime

import yaml

from src.clean import clean_dataframe
from src.export import export
from src.ingest import get_ingester
from src.logger import setup_logging
from src.quality import run_quality_checks
from src.validate import validate_all

setup_logging()
logger = logging.getLogger(__name__)

COURSE_KEYS = [
    "compliance",
    "career_planning",
    "e_biz",
    "fl4_artisans",
    "omusomo",
]


def load_configs(course_key: str, config_dir: str = "config"):
    with open(f"{config_dir}/base.yaml", encoding="utf-8") as f:
        base_config = yaml.safe_load(f)
    with open(f"{config_dir}/{course_key}.yaml", encoding="utf-8") as f:
        course_config = yaml.safe_load(f)
    return base_config, course_config


def merge_sources(data: dict, course_config: dict, base_config: dict):
    """Merge all loaded DataFrames into one on the email join key."""
    import pandas as pd

    join_key = base_config.get("join_key", "email")
    response_mapping = course_config.get("survey_response_mapping", {})

    progress = data.get("progress")
    post_course = data.get("post_course")
    pre_course = data.get("pre_course")
    user_export = data.get("user_export")
    master_ref = data.get("master_reference")
    individual = data.get("individual_profiling")
    business = data.get("business_profiling")
    enrollments = data.get("enrollments")

    if progress is None and post_course is None:
        raise ValueError("Cannot merge — both progress and post_course are None")

    df = progress.copy() if progress is not None else post_course.copy()
    if progress is not None and post_course is not None:
        response_cols = [v for v in response_mapping.values() if v is not None]
        keep_cols = [join_key] + [c for c in response_cols if c in post_course.columns]
        df = df.merge(post_course[keep_cols], on=join_key, how="left", suffixes=("", "_post"))

    if pre_course is not None:
        pre_cols = [c for c in pre_course.columns if c.startswith("Response") or c == join_key]
        df = df.merge(pre_course[pre_cols], on=join_key, how="left", suffixes=("", "_pre"))

    if user_export is not None:
        phone_cols = [join_key] + [
            c for c in user_export.columns
            if any(kw in c.lower() for kw in ("phone", "mobile", "tel")) and c != join_key
        ]
        if len(phone_cols) > 1:
            df = df.merge(user_export[phone_cols], on=join_key, how="left", suffixes=("", "_usr"))

    if master_ref is not None:
        df = df.merge(master_ref, on=join_key, how="left", suffixes=("_x", "_y"))

    for src in [individual, business, enrollments]:
        if src is not None:
            df = df.merge(src, on=join_key, how="left", suffixes=("_x", "_y"))

    # Rename survey response columns to friendly names
    rename_map = {}
    friendly = {"gender": "Gender", "age_group": "Age group", "hub": "ESO Hub", "district": "District"}
    for field_name, response_col in response_mapping.items():
        if response_col and response_col in df.columns and field_name in friendly:
            rename_map[response_col] = friendly[field_name]
    if rename_map:
        df = df.rename(columns=rename_map)

    logger.info(f"Merge complete: {len(df)} rows, {len(df.columns)} columns")
    return df


def run_course(course_key: str, config_dir: str = "config") -> dict:
    """Run the full pipeline for one course."""
    logger.info("=" * 55)
    logger.info(f"Starting: {course_key}")
    logger.info("=" * 55)

    base_config, course_config = load_configs(course_key, config_dir)
    reports_dir = base_config["paths"]["reports"]

    # 1. Ingest
    ingester = get_ingester(course_config, base_config)
    data = ingester.load()

    # 2. Validate
    validate_all(data, course_config, base_config)

    # 3. Merge
    df_merged = merge_sources(data, course_config, base_config)

    # 4. Clean
    df_clean = clean_dataframe(df_merged, base_config, course_config)

    # 5. Quality
    run_quality_checks(df_merged, df_clean, course_config, base_config, reports_dir)

    # 6. Export
    outputs = export(df_clean, course_config, base_config)

    logger.info(f"Done: {course_config['course_name']}")
    for dest, path in outputs.items():
        logger.info(f"  → {dest}: {path}")

    return outputs


def run_all(config_dir: str = "config") -> dict:
    """Run Academy first, then all 5 courses."""
    started = datetime.now()
    results = {}
    failed = []

    # Academy must run first
    try:
        results["academy"] = run_course("academy", config_dir)
    except Exception as e:
        logger.error(f"Academy FAILED: {e}")
        logger.error("Stopping — other courses depend on Academy output")
        raise

    # Then all courses
    for course_key in COURSE_KEYS:
        try:
            results[course_key] = run_course(course_key, config_dir)
        except Exception as e:
            logger.error(f"{course_key} FAILED: {e}")
            failed.append(course_key)

    duration = (datetime.now() - started).seconds
    logger.info("=" * 55)
    logger.info(f"Pipeline complete in {duration}s")
    logger.info(f"Completed: {list(results.keys())}")
    if failed:
        logger.warning(f"Failed: {failed}")
    logger.info("=" * 55)

    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        course_arg = sys.argv[1]
        if course_arg in ["academy"] + COURSE_KEYS:
            run_course(course_arg)
        else:
            print(f"Unknown course: {course_arg}")
            print(f"Available: academy, {', '.join(COURSE_KEYS)}")
            sys.exit(1)
    else:
        run_all()
