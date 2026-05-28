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
from backend.utils.mail_pool_cache import MailPoolCache


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


    def test_bind_mail_pool_email_disables_realtime_check_by_default(self):
        self.db.create_user('customer', 'zz123456', is_admin=False)
        user_id = self.db.conn.execute("SELECT id FROM users WHERE username = 'customer'").fetchone()[0]
        self.db.add_mail_pool_entry(
            'pool-realtime@outlook.com',
            'pw1',
            '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
            'M.C111_SN1.token-value$$'
        )

        result = self.db.bind_mail_pool_email(user_id, 'pool-realtime@outlook.com')

        email_row = self.db.conn.execute(
            "SELECT enable_realtime_check FROM emails WHERE id = ?",
            (result['email_id'],)
        ).fetchone()
        self.assertEqual(email_row['enable_realtime_check'], 0)

    def test_add_email_disables_realtime_check_by_default(self):
        self.db.create_user('customer2', 'zz123456', is_admin=False)
        user_id = self.db.conn.execute("SELECT id FROM users WHERE username = 'customer2'").fetchone()[0]

        email_id = self.db.add_email(
            user_id,
            'manual-only@outlook.com',
            'pw1',
            '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
            'M.C111_SN1.token-value$$',
            'outlook'
        )

        email_row = self.db.conn.execute(
            "SELECT enable_realtime_check FROM emails WHERE id = ?",
            (email_id,)
        ).fetchone()
        self.assertEqual(email_row['enable_realtime_check'], 0)

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

    def test_mail_pool_version_bumps_on_import_and_binding(self):
        self.db.create_user('customer', 'zz123456', is_admin=False)
        user_id = self.db.conn.execute("SELECT id FROM users WHERE username = 'customer'").fetchone()[0]
        initial_version = self.db.get_mail_pool_version()

        imported, _ = self.db.add_mail_pool_entry(
            'versioned@outlook.com',
            'pw1',
            '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
            'M.C111_SN1.token-value$$'
        )

        self.assertTrue(imported)
        after_import_version = self.db.get_mail_pool_version()
        self.assertGreater(after_import_version, initial_version)

        self.db.bind_mail_pool_email(user_id, 'versioned@outlook.com')

        self.assertGreater(self.db.get_mail_pool_version(), after_import_version)

    def test_batch_bind_mail_pool_uses_cached_entries_without_exposing_credentials(self):
        self.db.create_user('customer', 'zz123456', is_admin=False)
        self.db.create_user('other', 'zz123456', is_admin=False)
        user_id = self.db.conn.execute("SELECT id FROM users WHERE username = 'customer'").fetchone()[0]
        other_id = self.db.conn.execute("SELECT id FROM users WHERE username = 'other'").fetchone()[0]
        for email in ['first@outlook.com', 'second@outlook.com', 'taken@outlook.com']:
            self.db.add_mail_pool_entry(
                email,
                'pw1',
                '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
                'M.C111_SN1.token-value$$'
            )
        self.db.bind_mail_pool_email(other_id, 'taken@outlook.com')

        cached_entries = {
            email: self.db.get_mail_pool_entry_by_email(email)
            for email in ['first@outlook.com', 'second@outlook.com', 'taken@outlook.com']
        }
        lookup_calls = []

        def resolver(email):
            lookup_calls.append(email)
            return cached_entries.get(email)

        result = self.db.bind_mail_pool_emails(
            user_id,
            ['first@outlook.com', 'missing@outlook.com', 'taken@outlook.com', 'second@outlook.com'],
            resolver=resolver,
        )

        self.assertEqual(result['total'], 4)
        self.assertEqual(result['summary']['bound'], 2)
        self.assertEqual(result['summary']['not_found'], 1)
        self.assertEqual(result['summary']['assigned_to_other'], 1)
        self.assertTrue(self.db.email_exists(user_id, 'first@outlook.com'))
        self.assertTrue(self.db.email_exists(user_id, 'second@outlook.com'))
        self.assertEqual(lookup_calls, [
            'first@outlook.com',
            'missing@outlook.com',
            'taken@outlook.com',
            'second@outlook.com',
        ])
        for item in result['results']:
            self.assertNotIn('refresh_token', item)
            self.assertNotIn('password', item)
            self.assertNotIn('client_id', item)



class MailPoolCacheTestCase(unittest.TestCase):
    def test_cache_reloads_only_when_database_version_changes(self):
        class FakeDb:
            def __init__(self):
                self.version = 1
                self.load_count = 0
                self.rows = [{'email': 'cached@outlook.com', 'status': 'available'}]

            def get_mail_pool_version(self):
                return self.version

            def get_mail_pool_entries_for_cache(self):
                self.load_count += 1
                return list(self.rows)

        fake_db = FakeDb()
        cache = MailPoolCache(fake_db)

        self.assertEqual(cache.get('cached@outlook.com')['status'], 'available')
        self.assertEqual(cache.get('cached@outlook.com')['status'], 'available')
        self.assertEqual(fake_db.load_count, 1)

        fake_db.version = 2
        fake_db.rows = [{'email': 'cached@outlook.com', 'status': 'assigned'}]

        self.assertEqual(cache.get('cached@outlook.com')['status'], 'assigned')
        self.assertEqual(fake_db.load_count, 2)

    def test_get_many_uses_one_cache_snapshot_for_multiple_emails(self):
        class FakeDb:
            def __init__(self):
                self.version = 1
                self.load_count = 0
                self.rows = [
                    {'email': 'first@outlook.com', 'status': 'available'},
                    {'email': 'second@outlook.com', 'status': 'available'},
                ]

            def get_mail_pool_version(self):
                return self.version

            def get_mail_pool_entries_for_cache(self):
                self.load_count += 1
                return list(self.rows)

        fake_db = FakeDb()
        cache = MailPoolCache(fake_db)

        result = cache.get_many(['first@outlook.com', 'missing@outlook.com', 'SECOND@outlook.com'])

        self.assertEqual(set(result.keys()), {'first@outlook.com', 'second@outlook.com'})
        self.assertEqual(fake_db.load_count, 1)
        self.assertIsNot(result['first@outlook.com'], fake_db.rows[0])


class MailPoolApiTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.bind_mail_pool_email')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_bind_endpoint_binds_current_user_email_only_by_exact_address(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_bind,
        mock_cache,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'customer', 'is_admin': False}
        mock_cache.get.return_value = {'email': 'pool1@outlook.com', 'status': 'available'}
        mock_bind.return_value = {'status': 'bound', 'email_id': 7, 'email': 'pool1@outlook.com'}

        response = self.client.post(
            '/api/mail-pool/bind',
            json={'email': 'pool1@outlook.com'},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['email_id'], 7)
        mock_cache.get.assert_called_once_with('pool1@outlook.com')
        mock_bind.assert_called_once_with(
            99,
            'pool1@outlook.com',
            entry={'email': 'pool1@outlook.com', 'status': 'available'}
        )

    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.bind_mail_pool_email')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_bind_endpoint_returns_404_for_missing_pool_email(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_bind,
        mock_cache,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'customer', 'is_admin': False}
        mock_cache.get.return_value = None

        response = self.client.post(
            '/api/mail-pool/bind',
            json={'email': 'missing@outlook.com'},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 404)
        mock_cache.get.assert_called_once_with('missing@outlook.com')
        mock_bind.assert_not_called()

    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.bind_mail_pool_email')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_bind_endpoint_returns_409_when_pool_email_belongs_to_another_user(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_bind,
        mock_cache,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'customer', 'is_admin': False}
        mock_cache.get.return_value = {'email': 'pool1@outlook.com', 'assigned_user_id': 1}
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

    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.bind_mail_pool_emails')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_batch_bind_endpoint_accepts_one_email_per_line_and_returns_summary(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_batch_bind,
        mock_cache,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'customer', 'is_admin': False}
        mock_cache.get_many.return_value = {
            'a@outlook.com': {'email': 'a@outlook.com', 'status': 'available'}
        }
        mock_batch_bind.return_value = {
            'total': 3,
            'summary': {'bound': 1, 'already_bound': 1, 'not_found': 1},
            'results': [
                {'line': 1, 'email': 'a@outlook.com', 'status': 'bound', 'email_id': 7, 'message': '邮箱绑定成功'},
                {'line': 2, 'email': 'b@outlook.com', 'status': 'already_bound', 'email_id': 8, 'message': '邮箱已绑定，无需重复绑定'},
                {'line': 3, 'email': 'missing@outlook.com', 'status': 'not_found', 'message': '该邮箱不在可绑定邮箱库中'},
            ]
        }

        response = self.client.post(
            '/api/mail-pool/batch-bind',
            json={'emails': 'a@outlook.com\nb@outlook.com\nmissing@outlook.com'},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['summary']['bound'], 1)
        self.assertEqual(body['summary']['already_bound'], 1)
        self.assertEqual(body['summary']['not_found'], 1)
        self.assertNotIn('refresh_token', str(body))
        mock_batch_bind.assert_called_once()
        args, kwargs = mock_batch_bind.call_args
        self.assertEqual(args[0], 99)
        self.assertEqual(args[1], ['a@outlook.com', 'b@outlook.com', 'missing@outlook.com'])
        mock_cache.get_many.assert_called_once_with(['a@outlook.com', 'b@outlook.com', 'missing@outlook.com'])
        self.assertEqual(kwargs['resolver']('a@outlook.com')['email'], 'a@outlook.com')
        self.assertIsNone(kwargs['resolver']('missing@outlook.com'))


if __name__ == '__main__':
    unittest.main()
