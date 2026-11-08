import unittest
from unittest.mock import Mock

from scripts.load_test import load_data_into_table, verify_table_row_counts


class ImportWarningTests(unittest.TestCase):
    def test_truncated_data_rolls_back_instead_of_committing(self):
        pool = Mock()
        connection = pool.get_connection.return_value
        cursor = connection.cursor.return_value
        cursor.rowcount = 1
        cursor.fetchone.return_value = (1,)
        cursor.fetchall.return_value = [('Warning', 1265, 'Data truncated')]
        with self.assertRaisesRegex(RuntimeError, 'produced 1 warnings'):
            load_data_into_table(pool, '/tmp/customer.csv')
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()
        cursor.close.assert_called_once()
        connection.close.assert_called_once()

    def test_import_verification_commits_before_reading_counts(self):
        events = []

        class Connection:
            def commit(self):
                events.append("commit")

        class Cursor:
            def execute(self, query):
                events.append(query)

            def fetchone(self):
                return (5,)

        verify_table_row_counts(Connection(), Cursor(), {"warehouse": 5})
        self.assertEqual(
            events,
            ["commit", "SELECT COUNT(*) FROM `warehouse`"],
        )


if __name__ == '__main__':
    unittest.main()
