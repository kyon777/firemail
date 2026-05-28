import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.database.db import Database
from backend.app import app, email_processor
from backend.ws_server.handler import WebSocketHandler


class IpLimitDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'ip-limits.db'
        self.db = object.__new__(Database)
        self.db.connect_db(str(self.db_path))
        self.db.init_db()

    def tearDown(self):
        self.db.conn.close()
        self.temp_dir.cleanup()

    def test_ip_rate_limit_blocks_after_three_register_email_failures(self):
        ip = '203.0.113.10'

        first = self.db.record_ip_failure(ip, 'register_email_verify', block_after=3, block_hours=24)
        second = self.db.record_ip_failure(ip, 'register_email_verify', block_after=3, block_hours=24)
        third = self.db.record_ip_failure(ip, 'register_email_verify', block_after=3, block_hours=24)

        self.assertFalse(first['blocked'])
        self.assertFalse(second['blocked'])
        self.assertTrue(third['blocked'])
        self.assertTrue(self.db.is_ip_blocked(ip, 'register_email_verify')['blocked'])

    def test_ip_daily_check_limit_rejects_over_50_mailbox_checks(self):
        ip = '203.0.113.20'

        allowed = self.db.consume_ip_daily_limit(ip, 'email_check', amount=50, daily_limit=50)
        rejected = self.db.consume_ip_daily_limit(ip, 'email_check', amount=1, daily_limit=50)

        self.assertTrue(allowed['allowed'])
        self.assertEqual(allowed['remaining'], 0)
        self.assertFalse(rejected['allowed'])
        self.assertEqual(rejected['remaining'], 0)


class IpLimitApiTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()
        with email_processor.lock:
            email_processor.processing_emails.clear()

    def tearDown(self):
        with email_processor.lock:
            email_processor.processing_emails.clear()

    @patch('backend.app.db.create_user')
    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.record_ip_failure')
    @patch('backend.app.db.is_ip_blocked')
    @patch('backend.app.db.is_registration_allowed')
    def test_register_records_pool_email_failures_and_blocks_ip(
        self,
        mock_allowed,
        mock_blocked,
        mock_record_failure,
        mock_cache,
        mock_create_user,
    ):
        mock_allowed.return_value = True
        mock_blocked.return_value = {'blocked': False}
        mock_cache.get.return_value = None
        mock_record_failure.return_value = {'blocked': True, 'blocked_until': '2099-01-01T00:00:00'}

        response = self.client.post(
            '/api/auth/register',
            json={
                'username': 'customer',
                'password': 'zz123456',
                'verification_email': 'missing@outlook.com',
            },
            headers={'X-Forwarded-For': '203.0.113.30'}
        )

        self.assertEqual(response.status_code, 429)
        self.assertIn('失败次数过多', response.get_json()['error'])
        mock_record_failure.assert_called_once_with(
            '203.0.113.30',
            'register_email_verify',
            block_after=3,
            block_hours=24,
        )
        mock_create_user.assert_not_called()

    @patch('backend.app.email_processor.manual_thread_pool.submit')
    @patch('backend.app.db.consume_ip_daily_limit')
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_single_email_check_is_limited_to_50_per_ip_per_day(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_get_email_by_id,
        mock_consume_limit,
        mock_submit,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'tester', 'is_admin': False}
        mock_get_email_by_id.return_value = {'id': 1, 'user_id': 99, 'email': 'demo@outlook.com'}
        mock_consume_limit.return_value = {
            'allowed': False,
            'limit': 50,
            'remaining': 0,
            'reset_at': '2099-01-02T00:00:00',
        }

        response = self.client.post(
            '/api/emails/1/check',
            json={},
            headers={
                'Authorization': 'Bearer fake-token',
                'X-Forwarded-For': '203.0.113.40',
            }
        )

        self.assertEqual(response.status_code, 429)
        self.assertIn('每天最多只能检查50个邮箱验证码', response.get_json()['message'])
        mock_consume_limit.assert_called_once_with('203.0.113.40', 'email_check', amount=1, daily_limit=50)
        mock_submit.assert_not_called()

    @patch('backend.app.email_processor.check_emails')
    @patch('backend.app.db.consume_ip_daily_limit')
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_all_emails')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_batch_email_check_counts_each_mailbox_against_ip_daily_limit(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_get_all_emails,
        mock_get_email_by_id,
        mock_consume_limit,
        mock_check_emails,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'tester', 'is_admin': False}
        mock_get_all_emails.return_value = [
            {'id': 1, 'user_id': 99, 'email': 'a@outlook.com'},
            {'id': 2, 'user_id': 99, 'email': 'b@outlook.com'},
        ]
        mock_get_email_by_id.side_effect = lambda email_id: {
            1: {'id': 1, 'user_id': 99, 'email': 'a@outlook.com'},
            2: {'id': 2, 'user_id': 99, 'email': 'b@outlook.com'},
        }.get(email_id)
        mock_consume_limit.return_value = {
            'allowed': False,
            'limit': 50,
            'remaining': 1,
            'reset_at': '2099-01-02T00:00:00',
        }

        response = self.client.post(
            '/api/emails/batch_check',
            json={'email_ids': [1, 2]},
            headers={
                'Authorization': 'Bearer fake-token',
                'X-Forwarded-For': '203.0.113.50',
            }
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.get_json()['remaining'], 1)
        mock_consume_limit.assert_called_once_with('203.0.113.50', 'email_check', amount=2, daily_limit=50)
        mock_check_emails.assert_not_called()


class IpLimitWebSocketTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_check_emails_uses_same_ip_daily_limit(self):
        class FakeDb:
            def __init__(self):
                self.consume_calls = []

            def get_user_by_id(self, user_id):
                return {'id': user_id, 'username': 'tester', 'is_admin': False}

            def get_all_emails(self, user_id):
                return [
                    {'id': 1, 'user_id': user_id, 'email': 'a@outlook.com'},
                    {'id': 2, 'user_id': user_id, 'email': 'b@outlook.com'},
                ]

            def consume_ip_daily_limit(self, ip, action, amount=1, daily_limit=50):
                self.consume_calls.append((ip, action, amount, daily_limit))
                return {
                    'allowed': False,
                    'limit': daily_limit,
                    'remaining': 1,
                    'reset_at': '2099-01-02T00:00:00',
                }

        class FakeEmailProcessor:
            def __init__(self):
                self.checked = False

            def is_email_being_processed(self, email_id):
                return False

            def check_emails(self, email_ids, progress_callback):
                self.checked = True

        class FakeWebSocket:
            request_headers = {'X-Forwarded-For': '203.0.113.60'}
            remote_address = ('127.0.0.1', 12345)

            def __init__(self):
                self.sent = []

            async def send(self, message):
                self.sent.append(json.loads(message))

        handler = WebSocketHandler()
        fake_db = FakeDb()
        fake_processor = FakeEmailProcessor()
        handler.set_dependencies(fake_db, fake_processor)
        websocket = FakeWebSocket()

        await handler.handle_check_emails(websocket, 99, {'email_ids': [1, 2]})

        self.assertEqual(fake_db.consume_calls, [('203.0.113.60', 'email_check', 2, 50)])
        self.assertFalse(fake_processor.checked)
        self.assertEqual(websocket.sent[-1]['type'], 'warning')
        self.assertIn('每天最多只能检查50个邮箱验证码', websocket.sent[-1]['message'])


if __name__ == '__main__':
    unittest.main()
