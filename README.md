# TPC-DS MySQL Benchmark

This repository benchmarks two 99-query TPC-DS suites against MySQL at a
selected scale factor (SF) of 1, 2, 4, or 8:

- **Baseline:** `queries/qmod_combined/`
- **Optimized:** `queries/final_combined/`

The root-level `RUN_ME.sh` script handles one scale factor per run. It starts
the repository's Docker Compose MySQL service when needed, generates and
preprocesses that SF's dataset if missing, loads its MySQL database if missing,
runs both query suites once, and writes timings and a comparison graph.
Complete datasets and databases are reused, so rerunning for an already set up
SF proceeds directly to benchmarking.

## Requirements

- Windows 10/11 with Docker Desktop configured for Linux containers, or another
  host with Docker Compose v2 and Docker.
- Python 3.9 or newer.
- TPC-DS Toolkit 4.0.0, downloaded separately from the official TPC source and
  used in accordance with its EULA. Extract it into the repository root so the
  path `DSGen-software-code-4.0.0/tools/Makefile.suite` exists. If the archive
  extracts to a differently named folder, rename or move it to
  `DSGen-software-code-4.0.0`.
- Network access on the first generator run so Docker can download its Linux
  build image and C compiler packages.
- Substantial free disk space for generated files and their MySQL copies. In
  this checkout, the SF1/SF2/SF4/SF8 source CSVs alone occupy about 16.8 GiB;
  MySQL tables and indexes need additional space. Dataset generation also uses
  temporary staging space, and SF8 is the largest. Check available disk space
  before starting.
- Enough memory for MySQL to load and query the largest scale factor. Query
  runtimes depend on the machine and can be long.

The benchmark does not redistribute the TPC-DS toolkit. Download and extract
version 4.0.0 yourself as described above before running the workflow. The
generator is built inside Docker, so a host C compiler is not required.

## Install Python dependencies

Run these commands from the repository root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell prevents environment activation, either use
`.\.venv\Scripts\python.exe` directly or allow locally installed scripts to run
according to your organization's PowerShell policy.

## Run the workflow

Run from the repository root using Bash (including Git Bash or WSL on Windows):

```powershell
bash RUN_ME.sh
```

No scale factor argument defaults to SF1. To select a different scale:

```powershell
bash RUN_ME.sh 1
bash RUN_ME.sh 2
bash RUN_ME.sh 4
bash RUN_ME.sh 8
```

For the selected SF, the script:

1. Connects to the configured MySQL server, or starts the `mysql` Compose
   service if no MySQL server is reachable.
2. Reuses complete preprocessed CSVs in `data/<sf>/`. If any expected table
   file is absent, it builds `dsdgen` from your extracted toolkit inside
   Docker, generates that SF's data, and preprocesses it for MySQL. No external
   dataset download is needed. Docker downloads its build image and compiler
   packages if they are not already available.
3. Creates and loads the matching database (`tpcds` for SF1, or `tpcds<sf>`
   for SF2/SF4/SF8) only if it is missing.
4. Executes the baseline suite once and optimized suite once at the selected
   SF.
5. Appends per-query timings and statuses to the results CSV and saves one
   baseline-versus-optimized graph for that SF.

Invalid scale factors are rejected. The database loader recreates its target
database, so an existing but incomplete database causes the script to stop
unless `--force` is provided. To deliberately reload only the selected SF:

```powershell
bash RUN_ME.sh 4 --force
```

`--force` permits dropping and recreating the selected benchmark database. It
still reuses complete generated data. Use it only with disposable benchmark
databases.

## Rerun and other modes

When the selected database contains the expected TPC-DS tables and rows, the
normal command skips setup, data generation, and loading, then runs that SF's
benchmark again. If MySQL is stopped, the normal command attempts to start the
Compose service so it can connect to the existing data volume.

To run only against an already-running MySQL server and fail instead of trying
to start or set up anything:

```powershell
bash RUN_ME.sh 2 --benchmark-only
```

To prepare missing data and databases without running queries:

```powershell
bash RUN_ME.sh 8 --setup-only
```

`--benchmark-only` does not start Docker, generate data, or load the database.
It fails with an explanation if MySQL or the selected loaded database is
unavailable. `--benchmark-only` and `--setup-only` cannot be used together;
`--force` cannot be combined with `--benchmark-only`.

## MySQL connection settings

The Compose service listens on `127.0.0.1:3306`. Its local development root
password defaults to `1234`, matching the Python connection configuration.
Set connection overrides in PowerShell before starting the workflow:

```powershell
$env:TPCDS_MYSQL_HOST = "127.0.0.1"
$env:TPCDS_MYSQL_PORT = "3306"
$env:TPCDS_MYSQL_USER = "root"
$env:TPCDS_MYSQL_PASSWORD = "your-local-password"
bash RUN_ME.sh 1
```

Compose applies the root password when it initializes a new data volume. For an
already-initialized volume, changing the environment variable does not change
the MySQL account password; set it to the password already configured in that
volume. Do not use the example local defaults outside a disposable development
environment or commit personal credentials.

## Results

Each invocation uses a unique UTC run ID. Results are saved under `results/`:

- `query_comparison.csv` — appended, one row per query and scale factor, with
  baseline and optimized seconds, success/failure status, error messages, and
  run ID. Failed queries have an empty timing and a recorded error.
- `query_comparison_sf=<sf>_<run-id>.png` — grouped per-query comparison graph
  for the selected SF.
- `load_test_sf=<sf>_<run-id>.txt` — loader timing details for databases loaded
  during setup.

An execution error is recorded in the CSV and graph; after the benchmark
finishes, the script exits with a non-zero status if any query failed. Resolve
the reported database/query issue before treating that run as complete.

## Repository layout

- `RUN_ME.sh` — root entry point; accepts one optional scale factor (default 1).
- `scripts/run_benchmark.py` — setup, loading, benchmarking, and results
  workflow invoked by `RUN_ME.sh`.
- `scripts/power_test.py` — shared SQL reading and query timing functions.
- `scripts/load_test.py` — MySQL schema creation, data loading, indexes, and
  table analysis.
- `scripts/preprocess_data.py` — converts generated pipe-delimited files for
  MySQL `LOAD DATA LOCAL INFILE`.
- `tools/` — MySQL TPC-DS table and referential-integrity definitions.
- `DSGen-software-code-4.0.0/` — toolkit directory that you download and
  extract locally; it is not included in this repository.
- `queries/qmod_combined/` and `queries/final_combined/` — baseline and
  optimized query suites.
- `data/<sf>/` — generated/preprocessed source data for each scale factor.
- `results/` — benchmark CSV, graphs, and loader logs.

## Tests

Run the local tests without a live MySQL server:

```powershell
python -m unittest discover -s tests -v
```

## Attribution and licensing

This repository builds on the TPC-DS MySQL setup by
[isakovaad](https://github.com/isakovaad/TPC-DS-MySQL), with subsequent
scale-factor, MySQL compatibility, and query-optimization changes. TPC-DS
toolkit materials are downloaded separately and remain subject to the toolkit's
EULA and license notices. Review those terms before using or redistributing
toolkit materials. Identify benchmark results as non-comparable to official
TPC Benchmark Results unless specifically authorized by TPC.
