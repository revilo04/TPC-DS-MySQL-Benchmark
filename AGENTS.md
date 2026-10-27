# Repository Guidelines

## Project Structure & Module Organization
- `scripts/` contains Python loaders, sequential and concurrent benchmarks, data maintenance, monitoring, and plotting utilities.
- `tools/` contains schema SQL and the query-generation wrapper. The TPC-DS toolkit binaries, sources, and Makefile are not bundled; obtain and build the toolkit separately.
- `queries/` uses flat directories: `orig/` for originals, `qmod/` for MySQL compatibility, `prev_student_opt/` for inherited optimizations, `qmod_combined/` for the baseline, `our_opt/` for team changes, and `final_combined/` for the merged suite. Preserve filenames such as `query72.sql`.
- `results/` holds timings and plots; `TPC-DS_report.tex` is the report, and `specification/` holds reference material. Generated datasets belong outside the repository in `../data/<sf>/` and `../data-maintenance/<sf>/`.

## Build, Test, and Development Commands
Run commands from the repository root. The README recommends Python 3.9.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install seaborn psutil
python -m compileall -q scripts tools
python -m scripts.plot_benchmarks
```

`seaborn` and `psutil` are imported but missing from the requirements file. Compilation checks syntax without running benchmarks. Plotting regenerates analyses from the saved SF1/2/4/8 results.

`python -m scripts.main --sf 1` runs the full benchmark after setup: fix legacy `<sf>/qmod` path construction to match the flat query directories, provide throughput streams (the default `qstreams/` is absent), and configure MySQL and generated data.

## Coding Style & Naming Conventions
Use four-space Python indentation and `snake_case` functions, variables, and modules. Follow surrounding SQL formatting and preserve query semantics. Keep experimental rewrites in `our_opt/` and synchronize the corresponding `final_combined/` query. No formatter or linter configuration is present.

## Testing Guidelines
There is no dedicated unit-test framework or coverage requirement; `*_test.py` files are database benchmark drivers. Validate changes on a disposable SF1 database before larger runs. Compare baseline and optimized query results, then timings under matching hardware, MySQL settings, and cache conditions. Record failures separately from successful timings.

## Commit & Pull Request Guidelines
History mixes plain descriptions with `feat:`, `refactor:`, and `docs:` prefixes; prefer these prefixes with imperative summaries. PRs should describe affected queries/scripts, correctness checks, configuration, scale factors, and timing evidence. Link relevant issues and include plots when performance claims depend on them.

## Configuration & Data Safety
Load scripts drop and recreate databases; maintenance scripts modify data. Use disposable benchmark databases. Keep credentials out of commits and replace embedded connection settings locally. Do not commit generated datasets. Resource monitoring currently targets `mysqld.exe`; adapt it for macOS/Linux measurements.
