import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.database.db import Database


class ExistingDatabaseMigrationTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "legacy.db"

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                password TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE system_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT
            )
            """
        )
        conn.execute("INSERT INTO users (username, password, is_admin) VALUES ('admin', 'pw', 1)")
        conn.execute("INSERT INTO system_config (key, value) VALUES ('allow_register', 'false')")
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_existing_database_migration_adds_missing_columns_without_overwriting_config(self):
        db = object.__new__(Database)
        db.connect_db(str(self.db_path))

        try:
            db.migrate_existing_database()

            columns = [row[1] for row in db.conn.execute("PRAGMA table_info(emails)").fetchall()]
            self.assertIn("enable_realtime_check", columns)

            tables = {
                row[0]
                for row in db.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            self.assertIn("mail_records", tables)
            self.assertIn("attachments", tables)

            allow_register = db.conn.execute(
                "SELECT value FROM system_config WHERE key = 'allow_register'"
            ).fetchone()[0]
            self.assertEqual("false", allow_register)
        finally:
            db.conn.close()


if __name__ == "__main__":
    unittest.main()
