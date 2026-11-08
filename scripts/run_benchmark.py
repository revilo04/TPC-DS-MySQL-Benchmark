"""Prepare TPC-DS data and MySQL databases, then compare both query suites."""
import argparse
import csv
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mysql.connector

from scripts.config import BASELINE_QUERIES, OPTIMIZED_QUERIES, ROOT, database_name, mysql_config
from scripts.load_test import load_test
from scripts.power_test import execute_queries, read_sql_files
from scripts.preprocess_data import preprocess_file

SCALE_FACTORS = (1, 2, 4, 8)
TOOLKIT_DIR = ROOT / "DSGen-software-code-4.0.0" / "tools"
RESULTS_CSV = ROOT / "results" / "query_comparison.csv"
CSV_FIELDS = (
    "run_id",
    "scale_factor",
    "query",
    "baseline_seconds",
    "baseline_status",
    "baseline_error",
    "optimized_seconds",
    "optimized_status",
    "optimized_error",
)


def expected_tables():
    schema = (ROOT / "tools" / "tpcds.sql").read_text(encoding="utf-8")
    tables = re.findall(r"\bCREATE\s+TABLE\s+`?([A-Za-z0-9_]+)", schema, re.IGNORECASE)
    if not tables:
        raise RuntimeError(f"No table definitions found in {ROOT / 'tools' / 'tpcds.sql'}")
    return tuple(table.casefold() for table in tables)


def missing_dataset_tables(directory, tables):
    files = {path.stem.casefold(): path for path in directory.glob("*.csv")}
    return [
        table
        for table in tables
        if table not in files or files[table].stat().st_size == 0
    ]


def expected_foreign_keys():
    ri_sql = (ROOT / "tools" / "tpcds_ri.sql").read_text(encoding="utf-8")
    ri_sql = "\n".join(
        line for line in ri_sql.splitlines() if not line.lstrip().startswith("--")
    )
    return {
        match.group(1).casefold()
        for match in re.finditer(
            r"\badd\s+constraint\s+`?([A-Za-z0-9_]+)", ri_sql, re.IGNORECASE
        )
    }


def database_state(cursor, sf, tables):
    database = database_name(sf)
    cursor.execute(
        "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
        (database,),
    )
    if cursor.fetchone() is None:
        return False, False, ["database missing"]

    cursor.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'",
        (database,),
    )
    existing = {row[0].casefold() for row in cursor.fetchall()}
    missing = sorted(set(tables) - existing)
    if missing:
        return True, False, [f"tables missing: {', '.join(missing)}"]

    empty = []
    for table in tables:
        cursor.execute(f"SELECT 1 FROM `{database}`.`{table}` LIMIT 1")
        if cursor.fetchone() is None:
            empty.append(table)
    if empty:
        return True, False, [f"tables empty: {', '.join(empty)}"]

    cursor.execute(
        "SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
        "WHERE CONSTRAINT_SCHEMA = %s",
        (database,),
    )
    constraints = {row[0].casefold() for row in cursor.fetchall()}
    missing_constraints = sorted(expected_foreign_keys() - constraints)
    if missing_constraints:
        return True, False, [
            f"foreign keys missing: {', '.join(missing_constraints)}"
        ]

    cursor.execute(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'MV_INV'",
        (database,),
    )
    if cursor.fetchone() is None:
        return True, False, ["MV_INV missing"]
    cursor.execute(f"SELECT 1 FROM `{database}`.`MV_INV` LIMIT 1")
    if cursor.fetchone() is None:
        return True, False, ["MV_INV is empty"]
    return True, True, []


def connect_mysql():
    return mysql.connector.connect(
        **mysql_config(),
        charset="utf8",
        connection_timeout=5,
    )


def connection_available():
    try:
        connection = connect_mysql()
    except mysql.connector.Error as error:
        if error.errno == 1045:
            raise RuntimeError(
                "MySQL rejected the configured credentials; check TPCDS_MYSQL_USER "
                "and TPCDS_MYSQL_PASSWORD."
            ) from error
        return False
    connection.close()
    return True


def start_mysql_service(timeout=300):
    print("MySQL is not reachable; starting the Compose service.", flush=True)
    try:
        subprocess.run(
            ["docker", "compose", "up", "-d", "mysql"],
            cwd=ROOT,
            check=True,
        )
    except FileNotFoundError as error:
        raise RuntimeError("Docker is required to start MySQL; install Docker Desktop and retry.") from error
    except subprocess.CalledProcessError as error:
        raise RuntimeError("Docker Compose could not start MySQL.") from error

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if connection_available():
            return
        time.sleep(3)
    raise TimeoutError(f"MySQL did not become ready within {timeout} seconds.")


def generate_datasets(scale_factors, tables, run_id):
    data_root = ROOT / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    stages = {}
    with tempfile.TemporaryDirectory(prefix=f".tpcds_{run_id}_", dir=data_root) as temporary:
        staging_root = Path(temporary)
        for sf in scale_factors:
            stage = staging_root / str(sf)
            stage.mkdir()
            stages[sf] = stage

        container_commands = [
            "apt-get update -qq",
            "apt-get install -y --no-install-recommends build-essential >/dev/null",
            "mkdir -p /tmp/tpcds-tools",
            f"cp -a /workspace/{TOOLKIT_DIR.relative_to(ROOT).as_posix()}/. /tmp/tpcds-tools/",
            "cd /tmp/tpcds-tools",
            # The bundled sources rely on common-symbol behavior removed from modern GCC defaults.
            "make -f Makefile.suite OS=LINUX "
            "CFLAGS='-D_FILE_OFFSET_BITS=64 -D_LARGEFILE_SOURCE -DYYDEBUG "
            "-DLINUX -g -Wall -fcommon' dsdgen",
        ]
        for sf, stage in stages.items():
            output_directory = f"/workspace/{stage.relative_to(ROOT).as_posix()}"
            container_commands.append(
                f"./dsdgen -DIR {output_directory} -SCALE {sf} "
                "-VERBOSE Y -SUFFIX .dat -TERMINATE Y -RNGSEED 42"
            )

        command = [
            "docker",
            "run",
            "--rm",
            "--volume",
            f"{ROOT}:/workspace",
            "--workdir",
            "/workspace",
            "debian:bookworm-slim",
            "sh",
            "-ec",
            "\n".join(container_commands),
        ]
        print(f"Building the bundled TPC-DS generator and generating SF {', '.join(map(str, scale_factors))}.", flush=True)
        subprocess.run(command, cwd=ROOT, check=True)

        for sf, stage in stages.items():
            for source in sorted(stage.glob("*.dat")):
                preprocess_file(source)
                source.unlink()
            missing = missing_dataset_tables(stage, tables)
            if missing:
                raise RuntimeError(
                    f"Generator did not produce all SF{sf} tables: {', '.join(missing)}"
                )
            target = data_root / str(sf)
            target.mkdir(parents=True, exist_ok=True)
            generated = {path.stem.casefold(): path for path in stage.glob("*.csv")}
            for table in tables:
                shutil.copy2(generated[table], target / f"{table}.csv")


def ensure_datasets(scale_factors, tables, run_id):
    for sf in scale_factors:
        directory = ROOT / "data" / str(sf)
        for table in tables:
            raw_file = directory / f"{table}.dat"
            csv_file = directory / f"{table}.csv"
            source = raw_file if raw_file.is_file() else csv_file
            if source.is_file():
                preprocess_file(source)

    missing_by_sf = {
        sf: missing_dataset_tables(ROOT / "data" / str(sf), tables)
        for sf in scale_factors
    }
    needs_generation = [sf for sf, missing in missing_by_sf.items() if missing]
    for sf in needs_generation:
        missing = missing_by_sf[sf]
        print(f"SF{sf} data is incomplete ({len(missing)} table files missing); generating a fresh dataset.", flush=True)
    if needs_generation:
        generate_datasets(needs_generation, tables, run_id)
    else:
        scales = ", ".join(f"SF{sf}" for sf in scale_factors)
        print(f"Complete generated datasets found for {scales}; skipping generation.", flush=True)


def current_database_states(cursor, scale_factor, tables):
    return {scale_factor: database_state(cursor, scale_factor, tables)}


def prepare_databases(args, tables, run_id):
    if not connection_available():
        if args.benchmark_only:
            raise RuntimeError("--benchmark-only requires a reachable MySQL server; no setup was attempted.")
        start_mysql_service()

    connection = connect_mysql()
    cursor = None
    try:
        cursor = connection.cursor()
        states = current_database_states(cursor, args.scale_factor, tables)
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()

    exists, loaded, reasons = states[args.scale_factor]
    if args.benchmark_only:
        if not loaded:
            raise RuntimeError(
                f"Database {database_name(args.scale_factor)} is missing or incomplete "
                f"({', '.join(reasons)}); --benchmark-only will not set it up."
            )
        print(
            f"Database {database_name(args.scale_factor)} is ready; "
            "benchmark-only mode skipped setup.",
            flush=True,
        )
        return

    if loaded and not args.force:
        print(
            f"Database {database_name(args.scale_factor)} is ready; "
            "skipping database setup and data generation.",
            flush=True,
        )
        return

    if exists and not args.force:
        print(
            f"{database_name(args.scale_factor)} is incomplete "
            f"({'; '.join(reasons)}); attempting a safe resume without dropping "
            "already loaded tables.",
            flush=True,
        )

    ensure_datasets([args.scale_factor], tables, run_id)
    print(
        f"Loading {database_name(args.scale_factor)} from data/{args.scale_factor}.",
        flush=True,
    )
    load_test(args.scale_factor, run_id, resume=exists and not args.force)


def run_query_suite(sf, query_directory):
    queries = read_sql_files(str(query_directory))
    if not queries:
        raise RuntimeError(f"No SQL queries found in {query_directory}")
    connection = mysql.connector.connect(
        **mysql_config(sf),
        charset="utf8",
    )
    try:
        cursor = connection.cursor()
        try:
            return execute_queries(queries, cursor)
        finally:
            cursor.close()
    finally:
        connection.close()


def result_rows(sf, run_id, baseline, optimized):
    rows = []
    for query in sorted(set(baseline[0]) | set(optimized[0])):
        baseline_time = baseline[0].get(query)
        optimized_time = optimized[0].get(query)
        baseline_failure = baseline[1].get(query)
        optimized_failure = optimized[1].get(query)
        rows.append(
            {
                "run_id": run_id,
                "scale_factor": sf,
                "query": query,
                "baseline_seconds": "" if baseline_time is None else f"{baseline_time:.6f}",
                "baseline_status": "failed" if baseline_failure else "success",
                "baseline_error": "" if not baseline_failure else baseline_failure[1],
                "optimized_seconds": "" if optimized_time is None else f"{optimized_time:.6f}",
                "optimized_status": "failed" if optimized_failure else "success",
                "optimized_error": "" if not optimized_failure else optimized_failure[1],
            }
        )
    return rows


def append_results(rows):
    RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    write_header = not RESULTS_CSV.exists() or RESULTS_CSV.stat().st_size == 0
    with RESULTS_CSV.open("a", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def plot_scale_factor(sf, baseline, optimized, output_path):
    queries = sorted(set(baseline[0]) | set(optimized[0]))
    positions = list(range(len(queries)))
    baseline_values = [baseline[0].get(query) for query in queries]
    optimized_values = [optimized[0].get(query) for query in queries]
    successful_values = [
        value
        for value in baseline_values + optimized_values
        if value is not None
    ]
    use_log_scale = (
        len(successful_values) > 1
        and all(value > 0 for value in successful_values)
        and max(successful_values) / min(successful_values) >= 100
    )

    figure_height = min(32, max(8, len(queries) * 0.28))
    figure, axis = plt.subplots(figsize=(13, figure_height))
    baseline_y = [position - 0.16 for position in positions]
    optimized_y = [position + 0.16 for position in positions]
    axis.scatter(
        [
            value for value in baseline_values
            if value is not None and (value > 0 or not use_log_scale)
        ],
        [
            y for value, y in zip(baseline_values, baseline_y)
            if value is not None and (value > 0 or not use_log_scale)
        ],
        label="Baseline",
        marker="o",
        s=30,
        color="#2878B5",
        zorder=3,
    )
    axis.scatter(
        [
            value for value in optimized_values
            if value is not None and (value > 0 or not use_log_scale)
        ],
        [
            y for value, y in zip(optimized_values, optimized_y)
            if value is not None and (value > 0 or not use_log_scale)
        ],
        label="Optimized",
        marker="D",
        s=28,
        color="#E87500",
        zorder=3,
    )
    for values, y_values in (
        (baseline_values, baseline_y),
        (optimized_values, optimized_y),
    ):
        for value, y in zip(values, y_values):
            if value is None:
                axis.text(
                    0.01,
                    y,
                    "failed",
                    transform=axis.get_yaxis_transform(),
                    color="#B22222",
                    fontsize=7,
                    va="center",
                )

    axis.set_title(f"TPC-DS Query Execution Times - SF{sf}")
    axis.set_xlabel(
        "Execution time (seconds; logarithmic scale)"
        if use_log_scale
        else "Execution time (seconds)"
    )
    axis.set_ylabel("Query number")
    axis.set_yticks(positions)
    axis.set_yticklabels([str(query) for query in queries], fontsize=8)
    axis.invert_yaxis()
    if use_log_scale:
        axis.set_xscale("log")
        axis.set_xlim(min(successful_values) / 2, max(successful_values) * 2)
    else:
        maximum = max(successful_values, default=0)
        axis.set_xlim(0, maximum * 1.15 if maximum else 1)
    axis.legend(loc="lower right")
    axis.grid(axis="x", linestyle="--", alpha=0.35)
    figure.tight_layout()
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def run_benchmarks(run_id, scale_factor):
    baseline_directory = ROOT / BASELINE_QUERIES
    optimized_directory = ROOT / OPTIMIZED_QUERIES
    baseline_query_numbers = set(read_sql_files(str(baseline_directory)))
    optimized_query_numbers = set(read_sql_files(str(optimized_directory)))
    if not baseline_query_numbers or baseline_query_numbers != optimized_query_numbers:
        raise RuntimeError(
            "Baseline and optimized directories must contain the same non-empty query set."
        )

    overall_failures = 0
    results_directory = ROOT / "results"
    results_directory.mkdir(exist_ok=True)
    for sf in (scale_factor,):
        print(f"\n========== SF{sf} ==========", flush=True)
        print("Running baseline query suite once.", flush=True)
        baseline = run_query_suite(sf, baseline_directory)
        print("Running optimized query suite once.", flush=True)
        optimized = run_query_suite(sf, optimized_directory)

        rows = result_rows(sf, run_id, baseline, optimized)
        append_results(rows)
        graph_path = results_directory / f"query_comparison_sf={sf}_{run_id}.png"
        plot_scale_factor(sf, baseline, optimized, graph_path)
        failed = len(baseline[1]) + len(optimized[1])
        overall_failures += failed
        print(f"Saved SF{sf} results to {RESULTS_CSV} and {graph_path}.", flush=True)
        if failed:
            print(f"SF{sf}: {failed} query execution(s) failed; details are in the CSV.", flush=True)

    if overall_failures:
        raise RuntimeError(
            f"Benchmark finished with {overall_failures} failed query execution(s); "
            f"see {RESULTS_CSV}."
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "scale_factor",
        nargs="?",
        type=int,
        choices=SCALE_FACTORS,
        default=1,
        help="Scale factor to set up and benchmark (1, 2, 4, or 8; default: 1).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--benchmark-only",
        action="store_true",
        help="Use the selected existing MySQL database only; do not start services, generate data, or load it.",
    )
    mode.add_argument(
        "--setup-only",
        action="store_true",
        help="Prepare MySQL, generated datasets, and databases without running queries.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow dropping and reloading the selected benchmark database.",
    )
    args = parser.parse_args(argv)
    if args.benchmark_only and args.force:
        parser.error("--force cannot be combined with --benchmark-only.")
    return args


def main(argv=None):
    args = parse_args(argv)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    tables = expected_tables()
    prepare_databases(args, tables, run_id)
    if not args.setup_only:
        run_benchmarks(run_id, args.scale_factor)
    print("TPC-DS workflow completed.", flush=True)


if __name__ == "__main__":
    main()
