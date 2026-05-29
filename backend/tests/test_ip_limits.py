import sys
import json
import tempfile
import unittest
from datetime import datetime, timedelta
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

    def test_ip_rate_limit_helper_blocks_after_three_legacy_failures(self):
        ip = '203.0.113.10'

        first = self.db.record_ip_failure(ip, 'legacy_failure_action', block_after=3, block_hours=24)
        second = self.db.record_ip_failure(ip, 'legacy_failure_action', block_after=3, block_hours=24)
        third = self.db.record_ip_failure(ip, 'legacy_failure_action', block_after=3, block_hours=24)

        self.assertFalse(first['blocked'])
        self.assertFalse(second['blocked'])
        self.assertTrue(third['blocked'])
        self.assertTrue(self.db.is_ip_blocked(ip, 'legacy_failure_action')['blocked'])

    def test_ip_daily_limit_helper_remains_for_legacy_non_mailbox_actions(self):
        ip = '203.0.113.20'

        allowed = self.db.consume_ip_daily_limit(ip, 'legacy_action', amount=50, daily_limit=50)
        rejected = self.db.consume_ip_daily_limit(ip, 'legacy_action', amount=1, daily_limit=50)

        self.assertTrue(allowed['allowed'])
        self.assertEqual(allowed['remaining'], 0)
        self.assertFalse(rejected['allowed'])
        self.assertEqual(rejected['remaining'], 0)

    def test_email_check_daily_limit_counts_unique_mailboxes_per_user(self):
        user_id = 101
        t0 = datetime(2026, 5, 28, 12, 0, 0)

        first = self.db.consume_user_email_check_limits(user_id, [1], daily_limit=2, minute_limit=3, now=t0)
        repeated = self.db.consume_user_email_check_limits(user_id, [1], daily_limit=2, minute_limit=3, now=t0 + timedelta(seconds=10))
        second_unique = self.db.consume_user_email_check_limits(user_id, [2], daily_limit=2, minute_limit=3, now=t0 + timedelta(seconds=20))
        over_limit = self.db.consume_user_email_check_limits(user_id, [3], daily_limit=2, minute_limit=3, now=t0 + timedelta(seconds=30))

        self.assertTrue(first['allowed'])
        self.assertEqual(first['count'], 1)
        self.assertEqual(first['remaining'], 1)
        self.assertTrue(repeated['allowed'])
        self.assertEqual(repeated['count'], 1)
        self.assertEqual(repeated['remaining'], 1)
        self.assertTrue(second_unique['allowed'])
        self.assertEqual(second_unique['count'], 2)
        self.assertEqual(second_unique['remaining'], 0)
        self.assertFalse(over_limit['allowed'])
        self.assertEqual(over_limit['status'], 'rate_limited')
        self.assertEqual(over_limit['remaining'], 0)

    def test_email_check_daily_limit_isolated_between_users(self):
        t0 = datetime(2026, 5, 28, 12, 0, 0)

        user_one_first = self.db.consume_user_email_check_limits(201, [1], daily_limit=1, minute_limit=3, now=t0)
        user_one_second = self.db.consume_user_email_check_limits(201, [2], daily_limit=1, minute_limit=3, now=t0 + timedelta(seconds=10))
        user_two_first = self.db.consume_user_email_check_limits(202, [2], daily_limit=1, minute_limit=3, now=t0 + timedelta(seconds=10))

        self.assertTrue(user_one_first['allowed'])
        self.assertFalse(user_one_second['allowed'])
        self.assertEqual(user_one_second['status'], 'rate_limited')
        self.assertTrue(user_two_first['allowed'])
        self.assertEqual(user_two_first['remaining'], 0)

    def test_same_mailbox_fourth_check_within_one_minute_is_rate_limited_per_user(self):
        user_id = 301
        t0 = datetime(2026, 5, 28, 12, 0, 0)

        first = self.db.consume_user_email_check_limits(user_id, [9], daily_limit=50, minute_limit=3, now=t0)
        second = self.db.consume_user_email_check_limits(user_id, [9], daily_limit=50, minute_limit=3, now=t0 + timedelta(seconds=10))
        third = self.db.consume_user_email_check_limits(user_id, [9], daily_limit=50, minute_limit=3, now=t0 + timedelta(seconds=20))
        fourth = self.db.consume_user_email_check_limits(user_id, [9], daily_limit=50, minute_limit=3, now=t0 + timedelta(seconds=30))
        after_reset = self.db.consume_user_email_check_limits(user_id, [9], daily_limit=50, minute_limit=3, now=t0 + timedelta(seconds=61))

        self.assertTrue(first['allowed'])
        self.assertTrue(second['allowed'])
        self.assertTrue(third['allowed'])
        self.assertFalse(fourth['allowed'])
        self.assertEqual(fourth['status'], 'mailbox_rate_limited')
        self.assertEqual(fourth['email_id'], 9)
        self.assertGreaterEqual(fourth['retry_after'], 1)
        self.assertTrue(after_reset['allowed'])

    def test_batch_email_check_daily_limit_only_counts_new_mailboxes_per_user(self):
        user_id = 401
        t0 = datetime(2026, 5, 28, 12, 0, 0)

        first = self.db.consume_user_email_check_limits(user_id, [1, 2], daily_limit=3, minute_limit=3, now=t0)
        second = self.db.consume_user_email_check_limits(user_id, [2, 3], daily_limit=3, minute_limit=3, now=t0 + timedelta(seconds=10))
        third = self.db.consume_user_email_check_limits(user_id, [1, 4], daily_limit=3, minute_limit=3, now=t0 + timedelta(seconds=20))

        self.assertTrue(first['allowed'])
        self.assertEqual(first['count'], 2)
        self.assertEqual(first['remaining'], 1)
        self.assertTrue(second['allowed'])
        self.assertEqual(second['count'], 3)
        self.assertEqual(second['remaining'], 0)
        self.assertFalse(third['allowed'])
        self.assertEqual(third['status'], 'rate_limited')
        self.assertEqual(third['count'], 3)
        self.assertEqual(third['remaining'], 0)


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
    def test_register_does_not_use_ip_blocking_for_pool_email_failures(
        self,
        mock_allowed,
        mock_blocked,
        mock_record_failure,
        mock_cache,
        mock_create_user,
    ):
        mock_allowed.return_value = True
        mock_cache.get.return_value = None

        response = self.client.post(
            '/api/auth/register',
            json={
                'username': 'customer',
                'password': 'zz123456',
                'verification_email': 'missing@outlook.com',
            },
            headers={'X-Forwarded-For': '203.0.113.30'}
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], '验证邮箱不在可注册邮箱库中')
        mock_blocked.assert_not_called()
        mock_record_failure.assert_not_called()
        mock_create_user.assert_not_called()


    @patch('backend.app.db.create_user')
    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.record_ip_failure')
    @patch('backend.app.db.is_ip_blocked')
    @patch('backend.app.db.is_registration_allowed')
    def test_register_does_not_block_shared_docker_gateway_ip(
        self,
        mock_allowed,
        mock_blocked,
        mock_record_failure,
        mock_cache,
        mock_create_user,
    ):
        mock_allowed.return_value = True
        mock_blocked.return_value = {'blocked': False}
        mock_record_failure.return_value = {'blocked': False}
        mock_cache.get.return_value = None

        response = self.client.post(
            '/api/auth/register',
            json={
                'username': 'customer',
                'password': 'zz123456',
                'verification_email': 'missing@outlook.com',
            },
            headers={'X-Forwarded-For': '172.28.0.1'}
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], '验证邮箱不在可注册邮箱库中')
        mock_blocked.assert_not_called()
        mock_record_failure.assert_not_called()
        mock_create_user.assert_not_called()

    @patch('backend.app.email_processor.manual_thread_pool.submit')
    @patch('backend.app.db.consume_user_email_check_limits', create=True)
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_single_email_check_uses_user_daily_limit(
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
            'status': 'rate_limited',
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
        mock_consume_limit.assert_called_once_with(99, [1], daily_limit=50, minute_limit=3)
        mock_submit.assert_not_called()

    @patch('backend.app.email_processor.manual_thread_pool.submit')
    @patch('backend.app.db.consume_user_email_check_limits', create=True)
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_single_email_fourth_minute_check_returns_429(
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
            'status': 'mailbox_rate_limited',
            'email_id': 1,
            'limit': 3,
            'remaining': 0,
            'retry_after': 31,
            'reset_at': '2099-01-02T00:00:00',
            'message': '同一个邮箱1分钟最多检查3次，请稍后再试',
        }

        response = self.client.post(
            '/api/emails/1/check',
            json={},
            headers={
                'Authorization': 'Bearer fake-token',
                'X-Forwarded-For': '203.0.113.41',
            }
        )

        self.assertEqual(response.status_code, 429)
        body = response.get_json()
        self.assertEqual(body['status'], 'mailbox_rate_limited')
        self.assertEqual(body['retry_after'], 31)
        mock_submit.assert_not_called()

    @patch('backend.app.email_processor.check_emails')
    @patch('backend.app.db.consume_user_email_check_limits', create=True)
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_all_emails')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_batch_email_check_uses_user_daily_limit(
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
            'status': 'rate_limited',
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
        mock_consume_limit.assert_called_once_with(99, [1, 2], daily_limit=50, minute_limit=3)
        mock_check_emails.assert_not_called()


class IpLimitWebSocketTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_websocket_check_emails_uses_user_daily_limit(self):
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

            def consume_user_email_check_limits(self, user_id, email_ids, daily_limit=50, minute_limit=3):
                self.consume_calls.append((user_id, email_ids, daily_limit, minute_limit))
                return {
                    'allowed': False,
                    'status': 'rate_limited',
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

        self.assertEqual(fake_db.consume_calls, [(99, [1, 2], 50, 3)])
        self.assertFalse(fake_processor.checked)
        self.assertEqual(websocket.sent[-1]['type'], 'warning')
        self.assertIn('每天最多只能检查50个邮箱验证码', websocket.sent[-1]['message'])

    async def test_websocket_same_mailbox_minute_limit_sends_429_warning(self):
        class FakeDb:
            def get_user_by_id(self, user_id):
                return {'id': user_id, 'username': 'tester', 'is_admin': False}

            def get_all_emails(self, user_id):
                return [{'id': 1, 'user_id': user_id, 'email': 'a@outlook.com'}]

            def consume_user_email_check_limits(self, user_id, email_ids, daily_limit=50, minute_limit=3):
                return {
                    'allowed': False,
                    'status': 'mailbox_rate_limited',
                    'email_id': 1,
                    'limit': minute_limit,
                    'remaining': 0,
                    'retry_after': 30,
                    'reset_at': '2099-01-02T00:00:00',
                    'message': '同一个邮箱1分钟最多检查3次，请稍后再试',
                }

        class FakeEmailProcessor:
            def __init__(self):
                self.checked = False

            def is_email_being_processed(self, email_id):
                return False

            def check_emails(self, email_ids, progress_callback):
                self.checked = True

        class FakeWebSocket:
            request_headers = {'X-Forwarded-For': '203.0.113.61'}
            remote_address = ('127.0.0.1', 12345)

            def __init__(self):
                self.sent = []

            async def send(self, message):
                self.sent.append(json.loads(message))

        handler = WebSocketHandler()
        fake_processor = FakeEmailProcessor()
        handler.set_dependencies(FakeDb(), fake_processor)
        websocket = FakeWebSocket()

        await handler.handle_check_emails(websocket, 99, {'email_ids': [1]})

        self.assertFalse(fake_processor.checked)
        self.assertEqual(websocket.sent[-1]['type'], 'warning')
        self.assertEqual(websocket.sent[-1]['status'], 'mailbox_rate_limited')
        self.assertEqual(websocket.sent[-1]['retry_after'], 30)


if __name__ == '__main__':
    unittest.main()
