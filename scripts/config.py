"""Shared local settings; override connection values with TPCDS_MYSQL_* variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_QUERIES = "queries/qmod_combined"
OPTIMIZED_QUERIES = "queries/final_combined"


def database_name(sf):
    if sf < 1:
        raise ValueError("Scale factor must be positive")
    return "tpcds" if sf == 1 else f"tpcds{sf}"


def mysql_config(sf=None, *, local_infile=False):
    config = {
        "host": os.getenv("TPCDS_MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("TPCDS_MYSQL_PORT", "3306")),
        "user": os.getenv("TPCDS_MYSQL_USER", "root"),
        "password": os.getenv("TPCDS_MYSQL_PASSWORD", ""),
        "consume_results": True,
        "allow_local_infile": local_infile,
    }
    if sf is not None:
        config["database"] = database_name(sf)
    return config


def query_directory(value):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_dir() or not any(path.glob("*.sql")):
        raise FileNotFoundError(f"No SQL files in {path}")
    return str(path)
