import json
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
from backend.ws_server.handler import WebSocketHandler


OPENAI_SENDER = 'openai.com'


class CustomerSenderFilterDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'sender-filter.db'
        self.db = object.__new__(Database)
        self.db.connect_db(str(self.db_path))
        self.db.init_db()
        self.db.create_user('customer', 'zz123456', is_admin=False)
        self.user_id = self.db.conn.execute(
            "SELECT id FROM users WHERE username = 'customer'"
        ).fetchone()['id']
        self.email_id = self.db.add_email(
            self.user_id,
            'customer@outlook.com',
            'pw',
            'client-id',
            'refresh-token',
            'outlook'
        )

    def tearDown(self):
        self.db.conn.close()
        self.temp_dir.cleanup()

    def test_get_mail_records_can_filter_openai_domain_sender_case_insensitively(self):
        self.db.add_mail_record(
            self.email_id,
            'OpenAI code',
            'OpenAI <noreply@tm.openai.com>',
            '2026-05-28 10:00:00',
            'code 123456',
            folder='INBOX'
        )
        self.db.add_mail_record(
            self.email_id,
            'Other code',
            'other@example.com',
            '2026-05-28 10:01:00',
            'other',
            folder='INBOX'
        )
        self.db.add_mail_record(
            self.email_id,
            'Upper sender',
            'NOREPLY@TM.OPENAI.COM',
            '2026-05-28 10:02:00',
            'code 654321',
            folder='Junk'
        )
        self.db.add_mail_record(
            self.email_id,
            'Rust safety',
            'rustandsafety@tm.openai.com',
            '2026-05-28 10:03:00',
            'code 888999',
            folder='INBOX'
        )

        records = self.db.get_mail_records(self.email_id, sender_filter=OPENAI_SENDER)

        self.assertEqual(
            [record['subject'] for record in records],
            ['Rust safety', 'Upper sender', 'OpenAI code']
        )


class CustomerSenderFilterApiTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('backend.app.db.get_mail_records')
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_customer_mail_records_endpoint_filters_to_openai_sender(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_get_email_by_id,
        mock_get_mail_records,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'customer', 'is_admin': False}
        mock_get_email_by_id.return_value = {'id': 7, 'user_id': 99, 'email': 'customer@outlook.com'}
        mock_get_mail_records.return_value = []

        response = self.client.get(
            '/api/emails/7/mail_records',
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        mock_get_mail_records.assert_called_once_with(7, sender_filter=OPENAI_SENDER)

    @patch('backend.app.db.get_mail_records')
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_admin_mail_records_endpoint_keeps_all_senders(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_get_email_by_id,
        mock_get_mail_records,
    ):
        mock_jwt_decode.return_value = {'user_id': 1}
        mock_get_user_by_id.return_value = {'id': 1, 'username': 'admin', 'is_admin': True}
        mock_get_email_by_id.return_value = {'id': 7, 'user_id': 99, 'email': 'customer@outlook.com'}
        mock_get_mail_records.return_value = []

        response = self.client.get(
            '/api/emails/7/mail_records',
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        mock_get_mail_records.assert_called_once_with(7)


class CustomerSenderFilterWebSocketTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_customer_websocket_mail_records_filters_to_openai_sender(self):
        class FakeDb:
            def __init__(self):
                self.calls = []

            def get_user_by_id(self, user_id):
                return {'id': user_id, 'username': 'customer', 'is_admin': False}

            def get_email_by_id(self, email_id, user_id=None):
                return {'id': email_id, 'user_id': user_id, 'email': 'customer@outlook.com'}

            def get_mail_records(self, email_id, sender_filter=None):
                self.calls.append((email_id, sender_filter))
                return []

        class FakeWebSocket:
            def __init__(self):
                self.sent = []

            async def send(self, message):
                self.sent.append(json.loads(message))

        handler = WebSocketHandler()
        fake_db = FakeDb()
        handler.set_dependencies(fake_db, email_processor=None)
        websocket = FakeWebSocket()

        await handler.handle_get_mail_records(websocket, 99, {'email_id': 7})

        self.assertEqual(fake_db.calls, [(7, OPENAI_SENDER)])
        self.assertEqual(websocket.sent[-1]['type'], 'mail_records')


if __name__ == '__main__':
    unittest.main()
