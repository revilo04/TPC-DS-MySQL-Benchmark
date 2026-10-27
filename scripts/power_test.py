import argparse
import os
import re
import time
from datetime import datetime
from threading import Event

import matplotlib.pyplot as plt
import mysql.connector
import pandas as pd
import seaborn as sns

from scripts import run_metadata
from scripts.config import BASELINE_QUERIES, OPTIMIZED_QUERIES, mysql_config, query_directory
from scripts.system_stats import stats_thread
from scripts.utils import extract_number

# MySQL ER_QUERY_TIMEOUT: statement interrupted by max_execution_time
QUERY_TIMEOUT_ERRNO = 3024


def read_sql_files(directory):
    queries = {}
    for filename in sorted(os.listdir(directory), key=extract_number):
        if filename.endswith(".sql"):
            with open(os.path.join(directory, filename), "r") as f:
                sql_content = f.read()
                sql_content = re.sub(r"--.*$", "", sql_content, flags=re.MULTILINE)
                sql_content = " ".join(sql_content.split())
                # only capture query number
                queries[extract_number(filename)] = sql_content
    return queries


# Function to execute queries and measure time
def execute_queries(
    queries,
    cursor,
    monitor_resource_utils=False,
    cold_results_dir=None,
    warm_results_dir=None,
    warmup=False
) -> tuple:
    """Return (query_times, failures); a failed query has time None and a (kind, message) failure."""
    query_times = {}
    failures = {}
    for filename, query in queries.items():
        print("Executing", filename, end="...\n")
        total_time = 0
        statements = [s.strip() for s in query.split(";") if s.strip()]
        try:
            for q in statements:
                if warmup:
                    # warm up the cache
                    print("executing warmup query")
                    elapsed_time = timed_statement(
                        cursor, q, monitor_resource_utils, cold_results_dir, filename
                    )
                    print("executed warmup query. took", elapsed_time, "seconds")
                total_time += timed_statement(
                    cursor, q, monitor_resource_utils, warm_results_dir, filename
                )
        except mysql.connector.Error as e:
            # Remaining statements of a failed query are skipped
            kind = "timeout" if e.errno == QUERY_TIMEOUT_ERRNO else "error"
            print(f"Error executing {filename} ({kind}): {e}")
            failures[filename] = (kind, str(e))
            total_time = None

        print(f"{filename} took {total_time} seconds")
        query_times[filename] = total_time
    return query_times, failures


def timed_statement(cursor, statement, monitor_resource_utils, results_dir, filename):
    """Execute one statement and fetch all rows; return elapsed seconds."""
    # Select process & start thread for recording metrics
    if monitor_resource_utils:
        condition = Event()
        stats_thread(condition, results_dir, filename)
    start_time = time.perf_counter()
    try:
        cursor.execute(statement)
        if cursor.with_rows:
            cursor.fetchall()
        while cursor.nextset():
            pass
        return time.perf_counter() - start_time
    finally:
        if monitor_resource_utils:
            # stop thread
            condition.set()
            # otherwise the thread writes the next print statement to the log as well
            time.sleep(0.5)


def successful_total(query_times):
    return sum(t for t in query_times.values() if t is not None)


# Function to save results to a file; failed queries are written as nan to keep line positions
def save_results_to_file(query_times, failures, scale_factor, uid):
    filename = f"results/pt_sf={scale_factor}_{uid}.txt"
    with open(filename, "w") as f:
        for time in query_times.values():
            f.write(f"{'nan' if time is None else time}\n")
        f.write(f"Total Time: {successful_total(query_times)}\n")
        if failures:
            f.write(f"Failed Queries: {', '.join(str(n) for n in failures)}\n")
    if failures:
        with open(f"results/pt_sf={scale_factor}_{uid}_failures.txt", "w") as f:
            for number, (kind, error) in failures.items():
                f.write(f"{number}\t{kind}\t{error}\n")


# Function to plot horizontal histogram
def plot_histogram(query_times, scale_factor, uid):
    filename = f"results/pt_sf={scale_factor}_{uid}.png"
    # Create the horizontal bar chart
    filenames, times = zip(*query_times.items())
    query_times_df = pd.DataFrame({"Query Number": filenames, "Time (seconds)": times}, dtype=float)
    # Create the Seaborn plot
    plt.figure(figsize=(10, 30))  # Increase the vertical size
    ax = sns.barplot(
        x="Time (seconds)", y="Query Number", data=query_times_df, orient="h"
    )
    # Label the axes
    plt.xlabel("Time (seconds)", fontsize=12)
    plt.ylabel("Query Number", fontsize=12)
    # Increase y-tick font size
    ax.set_yticklabels(ax.get_yticklabels(), size=5)
    # Add title
    plt.title(f"Time Taken for Each Query. SF={scale_factor}", fontsize=14)
    # Show the plot
    plt.savefig(filename)
    # plt.show()


def select_queries(queries, query_numbers=None):
    if not query_numbers:
        return queries
    missing = sorted(set(query_numbers) - set(queries))
    if missing:
        raise ValueError(f"Queries not found: {missing}")
    return {number: queries[number] for number in sorted(set(query_numbers))}


def power_test(scale_factor, queries_directory, uid, monitor_resource_utils=False, warmup=False,
               query_numbers=None, timeout=None):
    total_time = 0
    cold_results_directory_path = f"results/{scale_factor}_{uid}_cold"
    warm_results_directory_path = f"results/{scale_factor}_{uid}_warm"
    if monitor_resource_utils:
        if warmup and not os.path.exists(cold_results_directory_path):
            os.makedirs(cold_results_directory_path)
        if not os.path.exists(warm_results_directory_path):
            os.makedirs(warm_results_directory_path)
    conn = cursor = None
    queries_directory = query_directory(queries_directory)
    try:
        conn = mysql.connector.connect(
            **mysql_config(scale_factor), charset="utf8",
        )
        cursor = conn.cursor()
        if timeout:
            # Applies to each read-only SELECT statement in this session
            cursor.execute(f"SET SESSION max_execution_time = {round(timeout * 1000)}")
        queries = select_queries(read_sql_files(queries_directory), query_numbers)
        metadata = run_metadata.collect(
            cursor,
            {"scale_factor": scale_factor, "warmup": warmup, "timeout_seconds": timeout,
             "monitor_resource_utils": monitor_resource_utils},
            queries_directory,
            queries,
        )
        query_times, failures = execute_queries(
            queries,
            cursor,
            monitor_resource_utils,
            cold_results_directory_path,
            warm_results_directory_path,
            warmup
        )
        total_time = successful_total(query_times)
    except mysql.connector.Error as e:
        raise RuntimeError(f"Database query failed: {e}") from e
    except KeyboardInterrupt:
        raise
    else:
        save_results_to_file(query_times, failures, scale_factor, uid)
        metadata["total_time_seconds"] = total_time
        metadata["failures"] = {number: kind for number, (kind, _) in failures.items()}
        run_metadata.save(metadata, f"results/pt_sf={scale_factor}_{uid}_meta.json")
        plot_histogram(query_times, scale_factor, uid)
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
    if failures:
        # Results are saved, but an incomplete power test must not be used as a timing
        raise RuntimeError(f"{len(failures)} of {len(query_times)} queries failed: {list(failures)}")
    return total_time


def main(args):
    uid = datetime.now().strftime("%m-%d_%H-%M-%S")
    if args.query:
        uid += "_q" + "-".join(str(n) for n in sorted(set(args.query)))
    qdir = query_directory(args.qdir or (OPTIMIZED_QUERIES if args.opt else BASELINE_QUERIES))
    # Run the power test
    power_test(args.sf, qdir, uid, args.mru, args.warmup, args.query, args.timeout)


if __name__ == "__main__":
    # Specify the directory containing the SQL files
    parser = argparse.ArgumentParser(
        description="Perform power test (provide SF and location of queries)"
    )
    parser.add_argument(
        "--sf", type=int, default=1, help="An integer input for SF. Default is 1."
    )
    parser.add_argument(
        "--qdir",
        type=str,
        default=None,
        help="Exact SQL directory; defaults to baseline, or final_combined with --opt",
    )
    parser.add_argument(
        "--mru",
        action="store_true",
        default=False,
        help="Whether to monitor resource utils",
    )
    parser.add_argument(
        "--opt",
        action="store_true",
        default=False,
        help="Whether to use folder with optimized queries",
    )
    parser.add_argument(
        "--query",
        type=int,
        action="append",
        default=None,
        help="Run only this query number; repeat to select several",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Per-statement limit in seconds (MySQL max_execution_time); timeouts count as failures",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        default=False,
        help="Whether to use query warmup",
    )

    args = parser.parse_args()
    main(args)
