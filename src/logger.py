"""
logger.py — Structured logging setup

Call setup_logging() once at pipeline startup.
All modules use logging.getLogger(__name__) — they inherit this config.

Log output:
  - Console: INFO and above
  - File:    DEBUG and above, written to logs/pipeline_YYYY-MM-DD.log
"""

import logging
import os
from datetime import datetime


def setup_logging(log_dir: str = "logs", level: int = logging.DEBUG) -> None:
    """
    Configure logging for the pipeline.
    Creates a dated log file in log_dir/.
    """
    os.makedirs(log_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(log_dir, f"pipeline_{today}.log")

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers (avoid duplicate logs on re-runs)
    root_logger.handlers.clear()

    # Console handler — INFO and above
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(console)

    # File handler — DEBUG and above
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
    root_logger.addHandler(file_handler)

    logging.getLogger("prefect").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    logging.info(f"Logging initialised — file: {log_file}")
