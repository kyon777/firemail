import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.database.db import Database
from backend.app import app
from backend.utils.mail_pool_importer import sync_mail_pool_directory


VALID_STANDARD = 'pool1@outlook.com----pw1----9e5f94bc-e8a4-4e73-b8be-63364c29d753----M.C111_SN1.token-value$$'
VALID_LEGACY = 'pool2@outlook.com----pw2----M.C222_SN1.token-value$$----9e5f94bc-e8a4-4e73-b8be-63364c29d753'


class MailPoolDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'mail-pool.db'
        self.db = object.__new__(Database)
        self.db.connect_db(str(self.db_path))
        self.db.init_db()

    def tearDown(self):
        self.db.conn.close()
        self.temp_dir.cleanup()

    def test_init_db_creates_private_mail_pool_table(self):
        tables = {
            row[0]
            for row in self.db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn('mail_pool', tables)

        columns = [row[1] for row in self.db.conn.execute('PRAGMA table_info(mail_pool)').fetchall()]
        self.assertIn('email', columns)
        self.assertIn('assigned_user_id', columns)
        self.assertIn('status', columns)

    def test_sync_mail_pool_directory_imports_valid_lines_and_skips_duplicates(self):
        pool_dir = Path(self.temp_dir.name) / 'mail'
        pool_dir.mkdir()
        (pool_dir / 'daily.txt').write_text(
            '\n'.join([
                VALID_STANDARD,
                VALID_STANDARD,
                VALID_LEGACY,
                'bad-line',
                '',
            ]),
            encoding='utf-8'
        )

        result = sync_mail_pool_directory(self.db, str(pool_dir))

        self.assertEqual(result['total'], 4)
        self.assertEqual(result['imported'], 2)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(self.db.get_mail_pool_stats()['total'], 2)

    def test_bind_mail_pool_email_creates_user_email_without_exposing_pool_list(self):
        success, _ = self.db.create_user('customer', 'zz123456', is_admin=False)
        self.assertTrue(success)
        user_id = self.db.conn.execute("SELECT id FROM users WHERE username = 'customer'").fetchone()[0]
        imported, _ = self.db.add_mail_pool_entry(
            'pool1@outlook.com',
            'pw1',
            '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
            'M.C111_SN1.token-value$$',
            source_file='daily.txt'
        )
        self.assertTrue(imported)

        result = self.db.bind_mail_pool_email(user_id, 'pool1@outlook.com')

        self.assertEqual(result['status'], 'bound')
        self.assertGreater(result['email_id'], 0)
        self.assertTrue(self.db.email_exists(user_id, 'pool1@outlook.com'))
        pool_entry = self.db.get_mail_pool_entry_by_email('pool1@outlook.com')
        self.assertEqual(pool_entry['status'], 'assigned')
        self.assertEqual(pool_entry['assigned_user_id'], user_id)

    def test_bind_mail_pool_email_rejects_email_assigned_to_another_user(self):
        self.db.create_user('first', 'zz123456', is_admin=False)
        self.db.create_user('second', 'zz123456', is_admin=False)
        first_id = self.db.conn.execute("SELECT id FROM users WHERE username = 'first'").fetchone()[0]
        second_id = self.db.conn.execute("SELECT id FROM users WHERE username = 'second'").fetchone()[0]
        self.db.add_mail_pool_entry(
            'pool1@outlook.com',
            'pw1',
            '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
            'M.C111_SN1.token-value$$'
        )
        self.db.bind_mail_pool_email(first_id, 'pool1@outlook.com')

        result = self.db.bind_mail_pool_email(second_id, 'pool1@outlook.com')

        self.assertEqual(result['status'], 'assigned_to_other')


class MailPoolApiTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('backend.app.db.bind_mail_pool_email')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_bind_endpoint_binds_current_user_email_only_by_exact_address(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_bind,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'customer', 'is_admin': False}
        mock_bind.return_value = {'status': 'bound', 'email_id': 7, 'email': 'pool1@outlook.com'}

        response = self.client.post(
            '/api/mail-pool/bind',
            json={'email': 'pool1@outlook.com'},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['email_id'], 7)
        mock_bind.assert_called_once_with(99, 'pool1@outlook.com')

    @patch('backend.app.db.bind_mail_pool_email')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_bind_endpoint_returns_404_for_missing_pool_email(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_bind,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'customer', 'is_admin': False}
        mock_bind.return_value = {'status': 'not_found'}

        response = self.client.post(
            '/api/mail-pool/bind',
            json={'email': 'missing@outlook.com'},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 404)

    @patch('backend.app.db.bind_mail_pool_email')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_bind_endpoint_returns_409_when_pool_email_belongs_to_another_user(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_bind,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'customer', 'is_admin': False}
        mock_bind.return_value = {'status': 'assigned_to_other'}

        response = self.client.post(
            '/api/mail-pool/bind',
            json={'email': 'pool1@outlook.com'},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 409)

    @patch('backend.app.sync_mail_pool_directory')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_admin_sync_endpoint_requires_admin_and_returns_stats(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_sync,
    ):
        mock_jwt_decode.return_value = {'user_id': 1}
        mock_get_user_by_id.return_value = {'id': 1, 'username': 'admin', 'is_admin': True}
        mock_sync.return_value = {'total': 2, 'imported': 1, 'skipped': 1, 'failed': 0, 'failed_details': []}

        response = self.client.post(
            '/api/admin/mail-pool/sync',
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['imported'], 1)


if __name__ == '__main__':
    unittest.main()
