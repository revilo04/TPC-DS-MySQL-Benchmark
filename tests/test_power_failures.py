import math
import os
import tempfile
import unittest
from pathlib import Path

import mysql.connector

from scripts.power_test import execute_queries, save_results_to_file


class FakeCursor:
    def __init__(self, failing=(), errno=1054):
        self.failing = failing
        self.errno = errno
        self.executed = []
        self.with_rows = True

    def execute(self, statement):
        self.executed.append(statement)
        if statement in self.failing:
            raise mysql.connector.ProgrammingError("bad statement", errno=self.errno)

    def fetchall(self):
        return []

    def nextset(self):
        return None


class PowerFailureTests(unittest.TestCase):
    def test_failure_skips_rest_of_query_and_is_reported(self):
        cursor = FakeCursor(failing={"select bad"})
        queries = {1: "select 1", 2: "select bad; select 2", 3: "select 3"}
        times, failures = execute_queries(queries, cursor)
        self.assertEqual(cursor.executed, ["select 1", "select bad", "select 3"])
        self.assertIsNone(times[2])
        self.assertGreaterEqual(times[1], 0)
        self.assertEqual(failures, {2: ("error", "1054: bad statement")})

    def test_timeout_is_classified(self):
        cursor = FakeCursor(failing={"select slow"}, errno=3024)
        _, failures = execute_queries({1: "select slow"}, cursor)
        self.assertEqual(failures, {1: ("timeout", "3024: bad statement")})

    def test_failed_query_keeps_line_position(self):
        with tempfile.TemporaryDirectory() as directory:
            cwd = os.getcwd()
            os.chdir(directory)
            try:
                os.mkdir("results")
                save_results_to_file({1: 0.5, 2: None, 3: 1.5}, {2: ("error", "bad statement")}, 1, "t")
                lines = Path("results/pt_sf=1_t.txt").read_text().splitlines()
                errors = Path("results/pt_sf=1_t_failures.txt").read_text()
            finally:
                os.chdir(cwd)
        self.assertEqual(lines[0], "0.5")
        self.assertTrue(math.isnan(float(lines[1])))
        self.assertEqual(lines[2:], ["1.5", "Total Time: 2.0", "Failed Queries: 2"])
        self.assertEqual(errors, "2\terror\tbad statement\n")


if __name__ == '__main__':
    unittest.main()
