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

from backend.app import app
from backend.database.db import Database


class AdminUserEmailVisibilityDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'admin-user-emails.db'
        self.db = object.__new__(Database)
        self.db.connect_db(str(self.db_path))
        self.db.init_db()

    def tearDown(self):
        self.db.conn.close()
        self.temp_dir.cleanup()

    def test_get_all_users_with_emails_returns_sanitized_email_summary(self):
        self.db.create_user('customer', 'zz123456', is_admin=False)
        user_id = self.db.conn.execute(
            "SELECT id FROM users WHERE username = 'customer'"
        ).fetchone()['id']
        self.db.add_email(
            user_id,
            'customer@outlook.com',
            'secret-password',
            'client-id',
            'refresh-token',
            'outlook'
        )

        users = self.db.get_all_users_with_emails()

        customer = next(user for user in users if user['username'] == 'customer')
        self.assertEqual(customer['email_count'], 1)
        self.assertEqual(customer['emails'][0]['email'], 'customer@outlook.com')
        self.assertEqual(customer['emails'][0]['mail_type'], 'outlook')
        self.assertNotIn('password', customer['emails'][0])
        self.assertNotIn('refresh_token', customer['emails'][0])
        self.assertNotIn('client_id', customer['emails'][0])


class AdminUserEmailVisibilityApiTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('backend.app.db.get_all_users_with_emails')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_users_endpoint_includes_sanitized_email_summary_for_admins(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_get_all_users_with_emails,
    ):
        mock_jwt_decode.return_value = {'user_id': 1}
        mock_get_user_by_id.return_value = {'id': 1, 'username': 'admin', 'is_admin': True}
        mock_get_all_users_with_emails.return_value = [
            {
                'id': 2,
                'username': 'customer',
                'is_admin': False,
                'created_at': '2026-05-28 00:00:00',
                'email_count': 1,
                'emails': [
                    {
                        'id': 7,
                        'email': 'customer@outlook.com',
                        'mail_type': 'outlook',
                        'created_at': '2026-05-28 00:00:00',
                        'last_check_time': None,
                    }
                ],
            }
        ]

        response = self.client.get(
            '/api/users',
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body[0]['email_count'], 1)
        self.assertEqual(body[0]['emails'][0]['email'], 'customer@outlook.com')
        self.assertNotIn('password', str(body))
        self.assertNotIn('refresh-token', str(body))
        mock_get_all_users_with_emails.assert_called_once()


if __name__ == '__main__':
    unittest.main()
