import os
import tempfile
import unittest

from scripts.plot_report_figures import NUM_QUERIES, load_baseline, load_optimized


class ReportFigureDataTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def write(self, name, text):
        path = os.path.join(self.directory.name, name)
        with open(path, "w") as f:
            f.write(text)
        return path

    def test_baseline_reads_query_lines_until_total(self):
        lines = [str(q / 10) for q in range(1, NUM_QUERIES + 1)] + ["Total Time: 495.0", "Failed Queries: 3"]
        times = load_baseline(self.write("pt.txt", "\n".join(lines) + "\n"))
        self.assertEqual(len(times), NUM_QUERIES)
        self.assertEqual((times[1], times[99]), (0.1, 9.9))

    def test_baseline_rejects_incomplete_file(self):
        with self.assertRaises(ValueError):
            load_baseline(self.write("short.txt", "1.0\n2.0\nTotal Time: 3.0\n"))

    def test_optimized_uses_median_column_and_checks_completeness(self):
        header = "Scale_Factor,Query,Run1_Cold,Warm_Median_2_5\n"
        rows = "".join(f"1,{q},9.0,{q / 100}\n" for q in range(1, NUM_QUERIES + 1))
        times = load_optimized(self.write("ok.csv", header + rows))
        self.assertEqual(times[(1, 50)], 0.5)
        with self.assertRaises(ValueError):
            load_optimized(self.write("missing.csv", header + rows.replace("1,50,9.0,0.5\n", "")))


if __name__ == '__main__':
    unittest.main()
