import os
import re
import time
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import mysql.connector
from mysql.connector import pooling

from scripts.config import ROOT, database_name, mysql_config
from scripts.utils import log_time, reset_pool


def load_data_into_table(cnxpool, csv_file):
    # Acquire a connection from the pool
    conn = cnxpool.get_connection()
    cursor = conn.cursor()
    table_name = os.path.basename(csv_file)[:-4]
    # turn off autocommit, unique_checks, foreign_key_checks, sql_log_bin
    cursor.execute("SET autocommit=0;")
    cursor.execute("SET unique_checks=0;")
    cursor.execute("SET foreign_key_checks=0;")
    cursor.execute("SET sql_log_bin=0;")
    start_time = time.time()
    cursor.execute(
        (
            f"LOAD DATA LOCAL INFILE '{csv_file}' INTO TABLE {table_name} character set latin1 "
            "FIELDS TERMINATED BY '|' LINES TERMINATED BY '\\n';"
        )
    )
    elapsed_time = time.time() - start_time
    affected_rows = cursor.rowcount
    cursor.execute("SHOW COUNT(*) WARNINGS")
    warning_count = cursor.fetchone()[0]
    if warning_count:
        cursor.execute("SHOW WARNINGS LIMIT 5")
        warnings = cursor.fetchall()
        conn.rollback()
        cursor.close()
        conn.close()
        raise RuntimeError(f"Import of {table_name} produced {warning_count} warnings: {warnings}")
    # Release the connection back to the pool
    conn.commit()
    print(f"Loaded {table_name}: {affected_rows:,} rows in {elapsed_time:.1f}s", flush=True)
    cursor.close()
    conn.close()
    return elapsed_time


def verify_table_row_counts(conn, cursor, expected_rows):
    conn.commit()
    for table_name, row_count in expected_rows.items():
        cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
        actual_rows = cursor.fetchone()[0]
        if actual_rows != row_count:
            raise RuntimeError(
                f"Import verification failed for {table_name}: expected "
                f"{row_count} rows, found {actual_rows}."
            )


def load_test(sf: int, uid: str, resume: bool = False):
    data_directory = ROOT / "data" / str(sf)
    with (ROOT / "tools" / "tpcds.sql").open("r", encoding="utf-8") as schema_file:
        table_creation_sql = schema_file.read()
    table_statements = [
        statement.strip()
        for statement in table_creation_sql.split(";")
        if statement.strip()
    ]
    tables = [
        re.search(r"create\s+table\s+`?([A-Za-z0-9_]+)", statement, re.IGNORECASE).group(1)
        for statement in table_statements
    ]
    csv_files = {path.stem.casefold(): path for path in data_directory.glob("*.csv")}
    missing = [table for table in tables if table.casefold() not in csv_files]
    if missing:
        raise FileNotFoundError(
            f"Missing preprocessed CSV files in {data_directory}: {', '.join(missing)}; "
            "database unchanged"
        )
    results_directory = ROOT / "results"
    results_directory.mkdir(exist_ok=True)
    log_file = str(results_directory / f"load_test_sf={sf}_{uid}.txt")
    conn = mysql.connector.connect(**mysql_config(), use_pure=True)
    cursor = conn.cursor()
    db = database_name(sf)
    try:
        if not resume:
            cursor.execute(f"DROP DATABASE IF EXISTS `{db}`;")
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db}`;")
        cursor.execute(f"USE `{db}`;")
        cursor.execute("SET autocommit=0;")
        cursor.execute("SET unique_checks=0;")
        cursor.execute("SET foreign_key_checks=0;")
        cursor.execute("SET sql_log_bin=0;")

        initial_time = time.time()
        for statement in table_statements:
            match = re.search(
                r"create\s+table\s+`?([A-Za-z0-9_]+)", statement, re.IGNORECASE
            )
            table_name = match.group(1)
            cursor.execute(
                "SELECT 1 FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (db, table_name),
            )
            if cursor.fetchone() is None:
                cursor.execute(statement)
        conn.commit()
        log_time(log_file, "Table Creation", time.time() - initial_time)

        expected_rows = {}
        to_load = []
        for table_name in tables:
            csv_file = csv_files[table_name.casefold()]
            with csv_file.open("rb") as source:
                row_count = sum(1 for _ in source)
            expected_rows[table_name] = row_count
            cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
            existing_rows = cursor.fetchone()[0]
            if existing_rows == row_count:
                continue
            if existing_rows != 0:
                raise RuntimeError(
                    f"Cannot safely resume {table_name}: database has {existing_rows} "
                    f"rows but {csv_file.name} has {row_count}. The table was not changed."
                )
            to_load.append((table_name, csv_file))

        if to_load:
            dbconfig = dict(mysql_config(sf, local_infile=True), use_pure=True)
            cnxpool = pooling.MySQLConnectionPool(
                pool_name=f"insertion_{sf}_{uid[-8:]}",
                pool_size=8,
                **dbconfig,
            )
            csv_files_to_load = [
                (cnxpool, os.path.abspath(str(csv_file)).replace("\\", "\\\\"))
                for _, csv_file in to_load
            ]
            start_time = time.time()
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(lambda args: load_data_into_table(*args), csv_files_to_load))
            log_time(log_file, "Insertion", time.time() - start_time)
            for _ in range(8):
                reset_pool(cnxpool)

        verify_table_row_counts(conn, cursor, expected_rows)

        print("Adding missing foreign keys and indexes...", flush=True)
        with (ROOT / "tools" / "tpcds_ri.sql").open("r", encoding="utf-8") as ri_file:
            ri_statements = ri_file.read().split(";")
        cursor.execute(
            "SELECT CONSTRAINT_NAME FROM information_schema.REFERENTIAL_CONSTRAINTS "
            "WHERE CONSTRAINT_SCHEMA = %s",
            (db,),
        )
        existing_constraints = {row[0].casefold() for row in cursor.fetchall()}
        start_time = time.time()
        for statement in ri_statements:
            stmt = "\n".join(
                line for line in statement.splitlines() if not line.lstrip().startswith("--")
            ).strip()
            if not stmt:
                continue
            match = re.search(r"\badd\s+constraint\s+`?([A-Za-z0-9_]+)", stmt, re.IGNORECASE)
            if match and match.group(1).casefold() in existing_constraints:
                continue
            cursor.execute(stmt)
            if match:
                existing_constraints.add(match.group(1).casefold())
        conn.commit()
        log_time(log_file, "Referential Integrity", time.time() - start_time)

        print("Analyzing tables...", flush=True)
        start_time = time.time()
        for table_name in tables:
            cursor.execute(f"ANALYZE TABLE `{table_name}`")
        log_time(log_file, "Analyze Time", time.time() - start_time)

        print("Building MV_INV inventory summary...", flush=True)
        q39_ct = """CREATE TABLE IF NOT EXISTS MV_INV (
        W_WAREHOUSE_NAME varchar(20),
        W_WAREHOUSE_SK integer,
        I_ITEM_SK integer,
        D_MOY integer,
        D_YEAR integer,
        STDEV float,
        MEAN float
    );"""
        q39_data = """INSERT INTO MV_INV
        SELECT
            W_WAREHOUSE_NAME,
            W_WAREHOUSE_SK,
            I_ITEM_SK,
            D_MOY,
            D_YEAR,
            STDDEV_SAMP(INV_QUANTITY_ON_HAND) AS STDEV,
            AVG(INV_QUANTITY_ON_HAND) AS MEAN
        FROM date_dim
            JOIN inventory ON INV_DATE_SK = D_DATE_SK
            JOIN item ON INV_ITEM_SK = I_ITEM_SK
            JOIN warehouse ON INV_WAREHOUSE_SK = W_WAREHOUSE_SK
        GROUP BY W_WAREHOUSE_NAME, W_WAREHOUSE_SK, I_ITEM_SK, D_MOY, D_YEAR;"""
        start_time = time.time()
        cursor.execute(q39_ct)
        cursor.execute("TRUNCATE TABLE MV_INV")
        cursor.execute(q39_data)
        elapsed_time = time.time() - start_time
        log_time(log_file, "EADS", elapsed_time)
        cursor.execute("SET autocommit=1;")
        cursor.execute("SET unique_checks=1;")
        cursor.execute("SET foreign_key_checks=1;")
        cursor.execute("SET sql_log_bin=1;")
        total_time = time.time() - initial_time
        log_time(log_file, "Total", total_time)
        conn.commit()
        return total_time
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = ArgumentParser("load_test.py", description="Run load test")
    parser.add_argument("--sf", type=int, default=1, help="Scale factor")
    args = parser.parse_args()
    uid = datetime.now().strftime("%m-%d_%H-%M-%S")

    load_test(args.sf, uid)
