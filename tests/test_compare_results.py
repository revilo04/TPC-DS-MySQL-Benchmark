import unittest
from decimal import Decimal

from scripts.compare_results import compare_result_sets, compare_rows, split_statements


class CompareResultsTests(unittest.TestCase):
    def test_trailing_limit_is_dropped_only_when_requested(self):
        query = "select a from t where note = 'limit 5' order by a limit 100; select 1 LIMIT 3"
        self.assertEqual(split_statements(query), ["select a from t where note = 'limit 5' order by a limit 100",
                                                   "select 1 LIMIT 3"])
        self.assertEqual(split_statements(query, no_limit=True),
                         ["select a from t where note = 'limit 5' order by a", "select 1"])

    def test_decimal_is_exact_and_float_is_tolerant(self):
        self.assertEqual(compare_rows([(Decimal("1.50"), "x")], [(Decimal("1.5"), "x")])[0], "match")
        self.assertEqual(compare_rows([(Decimal("1.50"),)], [(Decimal("1.51"),)])[0], "mismatch")
        self.assertEqual(compare_rows([(0.1 + 0.2,)], [(0.3,)])[0], "match")
        self.assertEqual(compare_rows([(None, 1.0)], [(None, 1.0)])[0], "match")
        self.assertEqual(compare_rows([(None,)], [(0.0,)])[0], "mismatch")

    def test_order_only_and_row_count(self):
        base = [(1, "a"), (2, "b")]
        self.assertEqual(compare_rows(base, list(reversed(base)))[0], "order-only")
        status, detail = compare_rows(base, base[:1])
        self.assertEqual(status, "mismatch")
        self.assertIn("row count", detail)

    def test_worst_statement_outcome_wins(self):
        self.assertEqual(compare_result_sets([[(1,)], [(2,)]], [[(1,)], [(3,)]])[0], "mismatch")
        self.assertEqual(compare_result_sets([[(1,)]], [[(1,)], [(2,)]])[0], "mismatch")
        self.assertEqual(compare_result_sets([[(1,), (2,)]], [[(2,), (1,)]])[0], "order-only")


if __name__ == '__main__':
    unittest.main()
