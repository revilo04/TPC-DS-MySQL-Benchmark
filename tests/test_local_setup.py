import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.config import BASELINE_QUERIES, mysql_config, query_directory
from scripts.power_test import read_sql_files, select_queries
from scripts.preprocess_data import normalize_line, preprocess_file


class LocalSetupTests(unittest.TestCase):
    def test_connection_overrides_and_import_scope(self):
        with patch.dict(os.environ, {"TPCDS_MYSQL_HOST": "localhost", "TPCDS_MYSQL_PORT": "3307",
                                     "TPCDS_MYSQL_USER": "tester", "TPCDS_MYSQL_PASSWORD": "example"}):
            config = mysql_config(1)
            self.assertEqual((config['host'], config['port'], config['user'], config['password']),
                             ('localhost', 3307, 'tester', 'example'))
            self.assertEqual(config['database'], 'tpcds')
            self.assertFalse(config['allow_local_infile'])
            self.assertTrue(mysql_config(2, local_infile=True)['allow_local_infile'])
            self.assertEqual(mysql_config(2)['database'], 'tpcds2')

    def test_flat_queries_and_missing_directory(self):
        self.assertEqual(len(list(Path(query_directory(BASELINE_QUERIES)).glob('*.sql'))), 99)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                query_directory(directory)

    def test_single_query_selection(self):
        queries = read_sql_files(query_directory(BASELINE_QUERIES))
        self.assertEqual(list(select_queries(queries, [3])), [3])
        self.assertEqual(list(select_queries(queries, [72, 3, 3])), [3, 72])
        self.assertIs(select_queries(queries), queries)
        with self.assertRaises(ValueError):
            select_queries(queries, [100])

    def test_nulls_and_terminal_delimiter(self):
        self.assertEqual(normalize_line(b'|abc|||\r\n', True), b'\\N|abc|\\N|\\N\n')
        self.assertEqual(normalize_line(b'|abc|\n'), b'\\N|abc|\\N\n')
        self.assertEqual(normalize_line(b'1|x|\n', True), b'1|x\n')

    def test_preserves_raw_data_and_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / 'example.dat'
            original = b'1||x|\n2|value||\n'
            raw.write_bytes(original)
            csv = preprocess_file(raw)
            expected = b'1|\\N|x\n2|value|\\N\n'
            self.assertEqual(raw.read_bytes(), original)
            self.assertEqual(csv.read_bytes(), expected)
            preprocess_file(raw)
            preprocess_file(csv)
            self.assertEqual(csv.read_bytes(), expected)


if __name__ == '__main__':
    unittest.main()
