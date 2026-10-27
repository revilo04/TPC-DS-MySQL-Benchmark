"""Check that two versions of the same queries return identical rows."""
import argparse
import math
import re
import sys
import time
from collections import Counter

import mysql.connector

from scripts.config import mysql_config, query_directory
from scripts.power_test import read_sql_files, select_queries

TRAILING_LIMIT = re.compile(r"\s+limit\s+\d+\s*$", re.IGNORECASE)
FLOAT_REL_TOLERANCE = 1e-9
FLOAT_ABS_TOLERANCE = 1e-12


def split_statements(query, no_limit=False):
    statements = [s.strip() for s in query.split(";") if s.strip()]
    if no_limit:
        statements = [TRAILING_LIMIT.sub("", s) for s in statements]
    return statements


def fetch_result_sets(cursor, query, no_limit=False):
    """Execute each statement of a query and return one row list per statement."""
    result_sets = []
    for statement in split_statements(query, no_limit):
        cursor.execute(statement)
        result_sets.append(cursor.fetchall() if cursor.with_rows else [])
        while cursor.nextset():
            pass
    return result_sets


def values_equal(a, b):
    # Floats come from approximate aggregates such as STDDEV_SAMP; Decimal and text must match exactly
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        return math.isclose(float(a), float(b), rel_tol=FLOAT_REL_TOLERANCE, abs_tol=FLOAT_ABS_TOLERANCE)
    return a == b


def rows_equal(a, b):
    return len(a) == len(b) and all(values_equal(x, y) for x, y in zip(a, b))


def _hashable(row):
    return tuple(float(f"{v:.12g}") if isinstance(v, float) else v for v in row)


def compare_rows(base, cand):
    """Return ("match" | "order-only" | "mismatch", detail)."""
    if len(base) == len(cand) and all(rows_equal(a, b) for a, b in zip(base, cand)):
        return "match", f"{len(base)} rows"
    if len(base) == len(cand) and Counter(map(_hashable, base)) == Counter(map(_hashable, cand)):
        return "order-only", f"{len(base)} rows, same multiset in a different order"
    for i, (a, b) in enumerate(zip(base, cand)):
        if not rows_equal(a, b):
            return "mismatch", f"row {i}: base={a!r} cand={b!r} (base {len(base)} rows, cand {len(cand)} rows)"
    return "mismatch", f"row count differs: base {len(base)}, cand {len(cand)}"


def compare_result_sets(base_sets, cand_sets):
    if len(base_sets) != len(cand_sets):
        return "mismatch", f"statement count differs: base {len(base_sets)}, cand {len(cand_sets)}"
    outcomes = [compare_rows(b, c) for b, c in zip(base_sets, cand_sets)]
    for status in ("mismatch", "order-only"):
        details = [f"statement {i + 1}: {d}" for i, (s, d) in enumerate(outcomes) if s == status]
        if details:
            return status, "; ".join(details)
    return "match", "; ".join(d for _, d in outcomes)


def timed_fetch(cursor, query, no_limit):
    start = time.perf_counter()
    result_sets = fetch_result_sets(cursor, query, no_limit)
    return result_sets, time.perf_counter() - start


def main(args):
    base_queries = read_sql_files(query_directory(args.base))
    cand_queries = read_sql_files(query_directory(args.cand))
    numbers = args.query or sorted(set(base_queries) & set(cand_queries))
    base_queries = select_queries(base_queries, numbers)
    cand_queries = select_queries(cand_queries, numbers)

    conn = mysql.connector.connect(**mysql_config(args.sf), charset="utf8")
    cursor = conn.cursor()
    failed = []
    try:
        if args.timeout:
            cursor.execute(f"SET SESSION max_execution_time = {round(args.timeout * 1000)}")
        for number in base_queries:
            try:
                base, base_time = timed_fetch(cursor, base_queries[number], args.no_limit)
                cand, cand_time = timed_fetch(cursor, cand_queries[number], args.no_limit)
            except mysql.connector.Error as e:
                status, detail = "error", str(e)
            else:
                status, detail = compare_result_sets(base, cand)
                detail += f" (base {base_time:.2f}s, cand {cand_time:.2f}s)"
            print(f"Q{number}: {status} - {detail}")
            if status in ("mismatch", "error"):
                failed.append(number)
    finally:
        cursor.close()
        conn.close()
    if failed:
        print(f"Failed: {failed}")
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare the results of two query directories")
    parser.add_argument("--sf", type=int, default=1, help="Scale factor. Default is 1.")
    parser.add_argument("--base", required=True, help="Reference SQL directory")
    parser.add_argument("--cand", required=True, help="Candidate SQL directory")
    parser.add_argument(
        "--query",
        type=int,
        action="append",
        default=None,
        help="Query number to compare; repeat to select several. Defaults to queries in both directories",
    )
    parser.add_argument(
        "--no-limit",
        action="store_true",
        default=False,
        help="Drop a trailing LIMIT from each statement to compare complete results",
    )
    parser.add_argument("--timeout", type=float, default=None, help="Per-statement limit in seconds")
    sys.exit(main(parser.parse_args()))
