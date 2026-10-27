"""Save MySQL execution plans of selected queries under results/explain/."""
import argparse
import os
from datetime import datetime

import mysql.connector

from scripts.compare_results import split_statements
from scripts.config import ROOT, mysql_config, query_directory
from scripts.power_test import read_sql_files, select_queries


def explain(cursor, statement, analyze=False):
    # EXPLAIN ANALYZE executes the statement; FORMAT=TREE only estimates
    cursor.execute(("EXPLAIN ANALYZE " if analyze else "EXPLAIN FORMAT=TREE ") + statement)
    return "\n".join(row[0] for row in cursor.fetchall())


def main(args):
    queries_directory = query_directory(args.qdir)
    queries = select_queries(read_sql_files(queries_directory), args.query)
    out_dir = os.path.join(ROOT, "results", "explain", f"sf{args.sf}", os.path.basename(queries_directory))
    os.makedirs(out_dir, exist_ok=True)
    suffix = "_analyze" if args.analyze else ""

    conn = mysql.connector.connect(**mysql_config(args.sf), charset="utf8")
    cursor = conn.cursor()
    try:
        if args.timeout:
            cursor.execute(f"SET SESSION max_execution_time = {round(args.timeout * 1000)}")
        cursor.execute("SELECT @@version")
        version = cursor.fetchone()[0]
        for number, query in queries.items():
            plans = [explain(cursor, s, args.analyze) for s in split_statements(query)]
            path = os.path.join(out_dir, f"query{number}{suffix}.txt")
            with open(path, "w") as f:
                f.write(f"# {os.path.relpath(queries_directory, ROOT)}/query{number}.sql, SF{args.sf}, "
                        f"MySQL {version}, {datetime.now().astimezone().isoformat(timespec='seconds')}\n")
                f.write("\n\n".join(plans) + "\n")
            print(f"Q{number}: {os.path.relpath(path, ROOT)}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Save EXPLAIN output for selected queries")
    parser.add_argument("--sf", type=int, default=1, help="Scale factor. Default is 1.")
    parser.add_argument("--qdir", required=True, help="SQL directory")
    parser.add_argument("--query", type=int, action="append", default=None,
                        help="Query number; repeat to select several. Defaults to all queries")
    parser.add_argument("--analyze", action="store_true", default=False,
                        help="Use EXPLAIN ANALYZE (runs the query)")
    parser.add_argument("--timeout", type=float, default=None, help="Per-statement limit in seconds")
    main(parser.parse_args())
