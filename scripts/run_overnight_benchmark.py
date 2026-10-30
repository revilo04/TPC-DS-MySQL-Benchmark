import os
import re
import time
import csv
import subprocess
import statistics
import mysql.connector

# Configuration
QUERY_DIR = "queries/final_combined"
OUTPUT_CSV = "results/overnight_scientific_benchmark.csv"
SCALE_FACTORS = [
    (1, "tpcds"),
    (2, "tpcds2"),
    (4, "tpcds4"),
    (8, "tpcds8"),
]
NUM_RUNS = 5
STATEMENT_TIMEOUT_MS = 1800000  # 30-minute safety cap per statement (1,800,000 ms)
MYSQL_PASS = os.environ.get("MYSQL_PWD", "YOUR_MYSQL_PASSWORD")

def get_queries(directory):
    files = sorted(
        [f for f in os.listdir(directory) if f.endswith(".sql")],
        key=lambda x: int(re.search(r"\d+", x).group())
    )
    queries = []
    for fname in files:
        q_num = int(re.search(r"\d+", fname).group())
        with open(os.path.join(directory, fname), "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        cleaned = re.sub(r"--.*?$", "", raw, flags=re.MULTILINE)
        stmts = [s.strip() for s in cleaned.split(";") if s.strip()]
        queries.append((q_num, fname, stmts))
    return queries

def connect_and_configure(db_name=None):
    """Wait for MySQL to be ready, connect, and configure all memory/timeout settings."""
    for attempt in range(45):
        try:
            conn = mysql.connector.connect(
                host="localhost",
                user="root",
                password=MYSQL_PASS,
                charset="utf8"
            )
            cursor = conn.cursor()
            # Persist 14 GB (15,032,385,536 bytes) Buffer Pool + 1 GB Temp Tables across restarts
            cursor.execute("SET PERSIST innodb_buffer_pool_size = 15032385536;")
            cursor.execute("SET PERSIST internal_tmp_mem_storage_engine = MEMORY;")
            cursor.execute("SET PERSIST tmp_table_size = 1073741824;")
            cursor.execute("SET PERSIST max_heap_table_size = 1073741824;")
            cursor.execute("SET PERSIST temptable_max_ram = 1073741824;")
            cursor.execute("SET PERSIST join_buffer_size = 268435456;")
            cursor.execute("SET PERSIST sort_buffer_size = 67108864;")
            cursor.execute("SET PERSIST read_buffer_size = 8388608;")
            cursor.execute("SET PERSIST read_rnd_buffer_size = 16777216;")
            cursor.execute("SET PERSIST innodb_io_capacity = 4000;")
            cursor.execute("SET PERSIST innodb_io_capacity_max = 8000;")
            cursor.execute("SET PERSIST innodb_flush_log_at_trx_commit = 2;")

            # Apply session-level settings immediately
            cursor.execute("SET SESSION tmp_table_size = 1073741824;")
            cursor.execute("SET SESSION max_heap_table_size = 1073741824;")
            cursor.execute("SET SESSION join_buffer_size = 268435456;")
            cursor.execute("SET SESSION sort_buffer_size = 67108864;")
            cursor.execute(f"SET SESSION max_execution_time = {STATEMENT_TIMEOUT_MS};")
            if db_name:
                cursor.execute(f"USE {db_name};")
            return conn, cursor
        except Exception:
            time.sleep(2)
    raise RuntimeError("Could not connect to MySQL after 90 seconds.")

def restart_mysql_unattended():
    """Restart MySQL via Homebrew without sudo to clear the InnoDB buffer pool."""
    print("  [*] Restarting MySQL to flush InnoDB buffer pool for clean cold-cache start...", flush=True)
    subprocess.run(["brew", "services", "restart", "mysql"], check=False)
    time.sleep(6)

def save_csv(timings):
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Scale_Factor", "Query",
            "Run1_Cold", "Run2_Warm", "Run3_Warm", "Run4_Warm", "Run5_Warm",
            "Warm_Mean_2_5", "Warm_Std_2_5", "Warm_Median_2_5"
        ])
        for (s, q), r_list in sorted(timings.items()):
            padded = r_list + [None] * (NUM_RUNS - len(r_list))
            warm_valid = [x for x in r_list[1:] if x is not None and x >= 0]
            w_mean = statistics.mean(warm_valid) if warm_valid else None
            w_std = statistics.stdev(warm_valid) if len(warm_valid) > 1 else 0.0
            w_med = statistics.median(warm_valid) if warm_valid else None
            writer.writerow([
                s, q,
                *[f"{x:.6f}" if x is not None else "" for x in padded],
                f"{w_mean:.6f}" if w_mean is not None else "",
                f"{w_std:.6f}" if w_std is not None else "",
                f"{w_med:.6f}" if w_med is not None else ""
            ])

def main():
    os.makedirs("results", exist_ok=True)
    queries = get_queries(QUERY_DIR)
    print(f"Loaded {len(queries)} queries from {QUERY_DIR}", flush=True)

    # Persist 14GB RAM settings before the first restart
    conn, cursor = connect_and_configure()
    cursor.close()
    conn.close()

    timings = {}
    overall_start = time.time()

    for sf, db_name in SCALE_FACTORS:
        print(f"\n==========================================", flush=True)
        print(f"Preparing Scale Factor {sf} (Database: {db_name})", flush=True)
        print(f"==========================================", flush=True)
        restart_mysql_unattended()
        conn, cursor = connect_and_configure(db_name)

        for run_idx in range(1, NUM_RUNS + 1):
            run_type = "COLD (Warmup)" if run_idx == 1 else f"WARM #{run_idx - 1}"
            print(f"\n--- SF{sf} | Run {run_idx}/{NUM_RUNS} [{run_type}] ---", flush=True)
            sf_run_start = time.time()

            for q_num, fname, stmts in queries:
                t0 = time.time()
                try:
                    for stmt in stmts:
                        cursor.execute(stmt)
                        if cursor.with_rows:
                            cursor.fetchall()
                        while cursor.nextset():
                            pass
                    elapsed = time.time() - t0
                except Exception as e:
                    print(f"  [!] Query {q_num} error/timeout: {e}", flush=True)
                    elapsed = -1.0
                    try:
                        conn.ping(reconnect=True, attempts=3, delay=2)
                        cursor = conn.cursor()
                        cursor.execute(f"USE {db_name};")
                        cursor.execute(f"SET SESSION max_execution_time = {STATEMENT_TIMEOUT_MS};")
                    except Exception:
                        conn, cursor = connect_and_configure(db_name)

                timings.setdefault((sf, q_num), []).append(elapsed)
                print(f"  SF{sf} | Run {run_idx} | Q{q_num:<2}: {elapsed:.4f}s", flush=True)
                save_csv(timings)

            print(f"--> Finished SF{sf} Run {run_idx} in {time.time() - sf_run_start:.2f}s", flush=True)

        cursor.close()
        conn.close()

    print(f"\nAll runs complete in {(time.time() - overall_start)/3600:.2f} hours! Results saved to {OUTPUT_CSV}", flush=True)

if __name__ == "__main__":
    main()
