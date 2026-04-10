"""
pipeline.py — Master pipeline flow

Runs all 6 course pipelines in the correct order:
  1. Academy (must run first — produces master BFC reference file)
  2. Compliance
  3. Career Planning
  4. E-Business Essentials
  5. Financial Literacy 4 Artisans
  6. Omusomo Gwa NSSF

Academy runs first because 5 of the 6 courses merge against
final_cleaned_bfc.xlsx which Academy produces.

Usage:
  # Run everything
  python -m flows.pipeline

  # Run a single course only
  from flows.course_flow import run_course_flow
  run_course_flow(course_key="compliance")

  # Run from Makefile
  make run           # all courses
  make run-course course=compliance
"""

import logging
import sys
from datetime import datetime

from prefect import flow, get_run_logger

from flows.course_flow import run_academy_flow, run_course_flow

# Courses that run after Academy, in order
COURSE_KEYS = [
    "compliance",
    "career_planning",
    "e_biz",
    "fl4_artisans",
    "omusomo",
]


@flow(name="full-pipeline", log_prints=True)
def run_all(config_dir: str = "config") -> dict:
    """
    Run the full pipeline — Academy first, then all 5 courses.

    Returns:
        dict mapping course_key → output paths
    """
    logger = get_run_logger()
    started_at = datetime.now()
    logger.info(f"Full pipeline started at {started_at.isoformat()}")

    results = {}

    # Step 1: Academy must run first
    logger.info("=" * 50)
    logger.info("Running Academy (master pipeline)...")
    logger.info("=" * 50)
    try:
        results["academy"] = run_academy_flow(config_dir=config_dir)
        logger.info("Academy complete")
    except Exception as e:
        logger.error(f"Academy pipeline FAILED: {e}")
        logger.error("Cannot continue — other courses depend on Academy output")
        raise

    # Step 2: Run all course pipelines
    failed = []
    for course_key in COURSE_KEYS:
        logger.info("=" * 50)
        logger.info(f"Running course: {course_key}")
        logger.info("=" * 50)
        try:
            results[course_key] = run_course_flow(
                course_key=course_key,
                config_dir=config_dir,
            )
            logger.info(f"{course_key} complete")
        except Exception as e:
            logger.error(f"{course_key} pipeline FAILED: {e}")
            failed.append(course_key)
            # Continue running other courses even if one fails

    # Summary
    finished_at = datetime.now()
    duration = (finished_at - started_at).seconds
    logger.info("=" * 50)
    logger.info("PIPELINE SUMMARY")
    logger.info(f"Duration: {duration}s")
    logger.info(f"Completed: {list(results.keys())}")
    if failed:
        logger.warning(f"Failed: {failed}")
    logger.info("=" * 50)

    if failed:
        raise RuntimeError(
            f"Pipeline completed with failures: {failed}. "
            f"Check logs and quality reports in reports/ folder."
        )

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Run from terminal:
        python -m flows.pipeline              # run all courses
        python -m flows.pipeline compliance   # run one course only
    """
    if len(sys.argv) > 1:
        course_arg = sys.argv[1]
        if course_arg == "academy":
            run_academy_flow()
        elif course_arg in COURSE_KEYS:
            run_course_flow(course_key=course_arg)
        else:
            print(f"Unknown course: {course_arg}")
            print(f"Available: academy, {', '.join(COURSE_KEYS)}")
            sys.exit(1)
    else:
        run_all()
