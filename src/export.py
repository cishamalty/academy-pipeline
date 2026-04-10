"""
export.py — Data export to DuckDB and file outputs

Responsibilities:
- Write cleaned DataFrame to DuckDB (primary, persistent store)
- Write cleaned DataFrame to Excel or CSV (for stakeholders + Power BI)
- Date-stamp output files
- Keep processed/ folder organised by date
- Provide a read-back function so Power BI / downstream tools can query DuckDB

DuckDB is the source of truth. Excel/CSV outputs are derived from it.
When Power BI is connected directly to DuckDB, the file export becomes
optional (stakeholder convenience only).
"""

import logging
import os
from datetime import datetime

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dated_output_folder(base_folder: str) -> str:
    """Return a date-stamped subfolder path, creating it if needed."""
    today = datetime.now().strftime("%Y-%m-%d")
    folder = os.path.join(base_folder, today)
    os.makedirs(folder, exist_ok=True)
    return folder


def _output_filename(course_config: dict, extension: str) -> str:
    """Build the output filename with today's date appended."""
    base = course_config["output"]["filename"]
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{base}_{today}.{extension}"


# ---------------------------------------------------------------------------
# DuckDB export
# ---------------------------------------------------------------------------

def export_to_duckdb(
    df: pd.DataFrame,
    course_config: dict,
    base_config: dict,
) -> str:
    """
    Write the cleaned DataFrame to a DuckDB table.

    Each course gets its own table: course_{course_key}
    The table is replaced on each run (not appended) — DuckDB always
    reflects the latest cleaned data.

    Returns the DuckDB file path.
    """
    db_path = base_config["paths"]["duckdb"]
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    course_key = course_config.get("course_key", "unknown")
    table_prefix = base_config.get("output", {}).get("duckdb_table_prefix", "course_")
    table_name = f"{table_prefix}{course_key}"

    # Add run metadata columns
    df_to_write = df.copy()
    df_to_write["_loaded_at"] = datetime.now().isoformat()
    df_to_write["_course"] = course_config.get("course_name", course_key)

    conn = duckdb.connect(db_path)
    try:
        # Replace table on each run
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute(
            f"CREATE TABLE {table_name} AS SELECT * FROM df_to_write"
        )
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        logger.info(
            f"export_to_duckdb: wrote {row_count} rows to "
            f"table '{table_name}' in {db_path}"
        )
    finally:
        conn.close()

    return db_path


def export_master_to_duckdb(
    df: pd.DataFrame,
    base_config: dict,
) -> str:
    """
    Write the Academy master (BFC) DataFrame to DuckDB as a special table.
    Other course tables can join against this for enriched queries.
    """
    db_path = base_config["paths"]["duckdb"]
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

    df_to_write = df.copy()
    df_to_write["_loaded_at"] = datetime.now().isoformat()

    conn = duckdb.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS master_participants")
        conn.execute(
            "CREATE TABLE master_participants AS SELECT * FROM df_to_write"
        )
        row_count = conn.execute("SELECT COUNT(*) FROM master_participants").fetchone()[0]
        logger.info(
            f"export_master_to_duckdb: wrote {row_count} rows to "
            f"'master_participants' in {db_path}"
        )
    finally:
        conn.close()

    return db_path


# ---------------------------------------------------------------------------
# File export (Excel / CSV)
# ---------------------------------------------------------------------------

def export_to_excel(
    df: pd.DataFrame,
    course_config: dict,
    base_config: dict,
) -> str:
    """
    Write cleaned DataFrame to a date-stamped Excel file.
    Also writes the master reference file if this is the Academy pipeline.
    Returns the output file path.
    """
    processed_dir = base_config["paths"]["processed_data"]
    output_folder = _dated_output_folder(processed_dir)
    filename = _output_filename(course_config, "xlsx")
    filepath = os.path.join(output_folder, filename)

    # Remove timezone info from datetime columns (Excel doesn't support tz-aware)
    df_export = df.copy()
    for col in df_export.select_dtypes(include=["datetimetz"]).columns:
        df_export[col] = df_export[col].dt.tz_localize(None)

    df_export.to_excel(filepath, index=False, engine="xlsxwriter")
    logger.info(f"export_to_excel: wrote {len(df_export)} rows to {filepath}")

    # If this is the Academy master pipeline, also write the shared BFC reference file
    if course_config.get("is_master", False):
        master_path = course_config.get("master_output_file", "")
        if master_path:
            os.makedirs(os.path.dirname(master_path), exist_ok=True)
            df_export.to_excel(master_path, index=False, engine="xlsxwriter")
            logger.info(f"export_to_excel: master BFC written to {master_path}")

    return filepath


def export_to_csv(
    df: pd.DataFrame,
    course_config: dict,
    base_config: dict,
) -> str:
    """
    Write cleaned DataFrame to a date-stamped CSV file.
    Returns the output file path.
    """
    processed_dir = base_config["paths"]["processed_data"]
    output_folder = _dated_output_folder(processed_dir)
    filename = _output_filename(course_config, "csv")
    filepath = os.path.join(output_folder, filename)

    df.to_csv(filepath, index=False, encoding="utf-8-sig")  # utf-8-sig for Excel compatibility
    logger.info(f"export_to_csv: wrote {len(df)} rows to {filepath}")
    return filepath


# ---------------------------------------------------------------------------
# Master export orchestrator
# ---------------------------------------------------------------------------

def export(
    df: pd.DataFrame,
    course_config: dict,
    base_config: dict,
) -> dict[str, str]:
    """
    Export the cleaned DataFrame to all configured outputs.

    Always exports to DuckDB.
    Also exports to Excel or CSV depending on course config.

    Returns a dict of output paths:
        {
            "duckdb": "data/academy.duckdb",
            "file": "data/processed/2026-04-10/Business Compliance_2026-04-10.csv"
        }
    """
    outputs = {}

    # Always write to DuckDB
    if course_config.get("is_master", False):
        outputs["duckdb"] = export_master_to_duckdb(df, base_config)
    else:
        outputs["duckdb"] = export_to_duckdb(df, course_config, base_config)

    # Write to file based on course config
    output_format = course_config.get("output", {}).get("format", "csv")
    if output_format == "xlsx":
        outputs["file"] = export_to_excel(df, course_config, base_config)
    else:
        outputs["file"] = export_to_csv(df, course_config, base_config)

    logger.info(
        f"export: completed for '{course_config.get('course_name')}' — "
        f"outputs: {list(outputs.keys())}"
    )
    return outputs


# ---------------------------------------------------------------------------
# DuckDB query helpers (for Power BI / downstream use)
# ---------------------------------------------------------------------------

def query_duckdb(sql: str, db_path: str) -> pd.DataFrame:
    """
    Run a SQL query against the DuckDB database and return a DataFrame.

    Example usage:
        df = query_duckdb("SELECT * FROM course_compliance", "data/academy.duckdb")
        df = query_duckdb("SELECT course, COUNT(*) FROM course_compliance GROUP BY 1", db_path)
    """
    conn = duckdb.connect(db_path, read_only=True)
    try:
        result = conn.execute(sql).df()
        logger.info(f"query_duckdb: returned {len(result)} rows")
        return result
    finally:
        conn.close()


def list_tables(db_path: str) -> list[str]:
    """List all tables currently in the DuckDB database."""
    conn = duckdb.connect(db_path, read_only=True)
    try:
        tables = conn.execute("SHOW TABLES").df()["name"].tolist()
        return tables
    finally:
        conn.close()
