"""Record the environment of a benchmark run so timings can be traced and compared."""
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version

import psutil

from scripts.config import ROOT
from scripts.utils import extract_number

MYSQL_VARIABLES = (
    "version",
    "innodb_buffer_pool_size",
    "innodb_buffer_pool_instances",
    "innodb_flush_method",
    "innodb_flush_log_at_trx_commit",
    "join_buffer_size",
    "sort_buffer_size",
    "tmp_table_size",
    "max_heap_table_size",
    "optimizer_switch",
)


def _command(*args):
    try:
        return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _package_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def query_hashes(directory, query_numbers):
    """SHA-256 prefix of each selected query file as stored on disk."""
    hashes = {}
    for filename in os.listdir(directory):
        if filename.endswith(".sql") and extract_number(filename) in query_numbers:
            with open(os.path.join(directory, filename), "rb") as f:
                hashes[extract_number(filename)] = hashlib.sha256(f.read()).hexdigest()[:16]
    return dict(sorted(hashes.items()))


def server_state(cursor):
    names = ", ".join(f"@@{name}" for name in MYSQL_VARIABLES)
    cursor.execute(f"SELECT {names}")
    state = dict(zip(MYSQL_VARIABLES, cursor.fetchone()))
    cursor.execute("SHOW GLOBAL STATUS LIKE 'Uptime'")
    state["uptime_seconds"] = int(cursor.fetchone()[1])
    return state


def collect(cursor, settings, queries_directory, query_numbers):
    status = _command("git", "status", "--porcelain")
    return {
        "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "settings": settings,
        "query_directory": os.path.relpath(queries_directory, ROOT),
        "query_sha256": query_hashes(queries_directory, set(query_numbers)),
        "git": {
            "commit": _command("git", "rev-parse", "HEAD"),
            "dirty": bool(status) if status is not None else None,
        },
        "mysql": server_state(cursor),
        "python": sys.version.split()[0],
        "mysql_connector": _package_version("mysql-connector-python"),
        "machine": {
            "platform": platform.platform(),
            "cpu": _command("sysctl", "-n", "machdep.cpu.brand_string") or platform.processor(),
            "logical_cpus": os.cpu_count(),
            "memory_bytes": psutil.virtual_memory().total,
        },
    }


def save(metadata, path):
    metadata["finished_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(path, "w") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")
