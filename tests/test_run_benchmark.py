import csv
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from contextlib import ExitStack
from unittest.mock import Mock, patch

from scripts import run_benchmark
from scripts.config import mysql_config


class BenchmarkWorkflowTests(unittest.TestCase):
    def test_expected_table_list_matches_schema_and_datasets(self):
        tables = run_benchmark.expected_tables()
        self.assertEqual(len(tables), 25)
        self.assertEqual(len(set(tables)), len(tables))

    def test_mysql_default_password_matches_compose(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(mysql_config()["password"], "1234")

    def test_missing_dataset_tables_identifies_missing_and_empty_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "customer.csv").write_bytes(b"rows")
            (directory / "store.csv").write_bytes(b"")
            self.assertEqual(
                run_benchmark.missing_dataset_tables(directory, ("customer", "store", "date_dim")),
                ["store", "date_dim"],
            )

    def test_database_state_detects_absent_schema(self):
        class Cursor:
            def execute(self, *_):
                pass

            def fetchone(self):
                return None

        exists, loaded, reasons = run_benchmark.database_state(Cursor(), 1, ("customer",))
        self.assertFalse(exists)
        self.assertFalse(loaded)
        self.assertEqual(reasons, ["database missing"])

    def test_database_state_checks_expected_rows(self):
        class Cursor:
            def __init__(self):
                self.fetchone_calls = 0

            def execute(self, *_):
                pass

            def fetchone(self):
                self.fetchone_calls += 1
                return ("tpcds",) if self.fetchone_calls == 1 else (1,)

            def fetchall(self):
                return [("customer",), ("date_dim",)]

        self.assertEqual(
            run_benchmark.database_state(Cursor(), 1, ("customer", "date_dim")),
            (True, True, []),
        )

    def test_complete_databases_skip_dataset_generation_and_loading(self):
        connection = Mock()
        states = {4: (True, True, [])}
        with ExitStack() as stack:
            stack.enter_context(patch.object(run_benchmark, "connection_available", return_value=True))
            stack.enter_context(patch.object(run_benchmark, "connect_mysql", return_value=connection))
            stack.enter_context(patch.object(run_benchmark, "current_database_states", return_value=states))
            generate = stack.enter_context(patch.object(run_benchmark, "ensure_datasets"))
            load = stack.enter_context(patch.object(run_benchmark, "load_test"))
            run_benchmark.prepare_databases(
                SimpleNamespace(benchmark_only=False, force=False, scale_factor=4),
                ("customer",),
                "run-1",
            )
        generate.assert_not_called()
        load.assert_not_called()
        connection.close.assert_called_once()

    def test_scale_factor_argument_defaults_to_one_and_restricts_choices(self):
        self.assertEqual(run_benchmark.parse_args([]).scale_factor, 1)
        for sf in (1, 2, 4, 8):
            self.assertEqual(run_benchmark.parse_args([str(sf)]).scale_factor, sf)
        with self.assertRaises(SystemExit) as error:
            run_benchmark.parse_args(["3"])
        self.assertEqual(error.exception.code, 2)

    def test_benchmark_runs_only_the_selected_scale_factor(self):
        with ExitStack() as stack:
            read_queries = stack.enter_context(
                patch.object(run_benchmark, "read_sql_files", return_value={1: "SELECT 1"})
            )
            execute = stack.enter_context(
                patch.object(
                    run_benchmark,
                    "run_query_suite",
                    side_effect=[
                        ({1: 1.0}, {}),
                        ({1: 0.5}, {}),
                    ],
                )
            )
            stack.enter_context(patch.object(run_benchmark, "append_results"))
            stack.enter_context(patch.object(run_benchmark, "plot_scale_factor"))
            run_benchmark.run_benchmarks("run-1", 2)
        self.assertEqual(execute.call_count, 2)
        self.assertTrue(all(call.args[0] == 2 for call in execute.call_args_list))

    def test_result_rows_record_timings_and_failures(self):
        baseline = ({2: 1.25, 1: None}, {1: ("error", "bad SQL")})
        optimized = ({1: 0.5, 2: 0.75}, {})
        rows = run_benchmark.result_rows(4, "run-1", baseline, optimized)
        self.assertEqual([row["query"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["baseline_status"], "failed")
        self.assertEqual(rows[0]["baseline_error"], "bad SQL")
        self.assertEqual(rows[0]["optimized_seconds"], "0.500000")
        self.assertEqual(rows[1]["baseline_seconds"], "1.250000")
        self.assertEqual(rows[1]["optimized_status"], "success")

    def test_csv_appends_rows_and_writes_one_header(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_path = Path(temporary) / "results.csv"
            row = {field: "" for field in run_benchmark.CSV_FIELDS}
            row.update({"run_id": "run-1", "scale_factor": 1, "query": 1})
            with patch.object(run_benchmark, "RESULTS_CSV", output_path):
                run_benchmark.append_results([row])
                run_benchmark.append_results([row])
            with output_path.open(newline="", encoding="utf-8") as output:
                records = list(csv.DictReader(output))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["run_id"], "run-1")

    def test_scale_factor_plot_is_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            graph = Path(temporary) / "comparison.png"
            baseline = ({1: 1.0, 2: None}, {2: ("error", "timeout")})
            optimized = ({1: 0.5, 2: 0.75}, {})
            run_benchmark.plot_scale_factor(1, baseline, optimized, graph)
            self.assertTrue(graph.is_file())
            self.assertGreater(graph.stat().st_size, 0)

    def test_cli_rejects_force_with_benchmark_only(self):
        with self.assertRaises(SystemExit) as error:
            run_benchmark.parse_args(["--benchmark-only", "--force"])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
