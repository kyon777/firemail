import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.utils.email.outlook import OutlookIMAPAuthError, OutlookMailHandler
from backend.utils.email.mail_processor import EmailBatchProcessor


class OutlookGraphFallbackTestCase(unittest.TestCase):
    @patch('backend.utils.email.outlook.requests.post')
    def test_graph_token_refresh_sends_default_scope(self, mock_post):
        response = Mock()
        response.json.return_value = {'access_token': 'graph-access-token'}
        mock_post.return_value = response

        token = OutlookMailHandler.get_new_graph_access_token('refresh-token', 'client-id')

        self.assertEqual(token, 'graph-access-token')
        mock_post.assert_called_once()
        data = mock_post.call_args.kwargs['data']
        self.assertEqual(data['scope'], 'https://graph.microsoft.com/.default')


    @patch('backend.utils.email.outlook.requests.get')
    def test_fetch_graph_emails_reads_messages_from_folder(self, mock_get):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            'value': [{
                'id': 'msg-1',
                'subject': 'Your code',
                'from': {'emailAddress': {'name': 'OpenAI', 'address': 'noreply@tm.openai.com'}},
                'receivedDateTime': '2026-05-30T01:02:03Z',
                'body': {'content': '<p>654321</p>'},
            }]
        }
        response.raise_for_status.return_value = None
        mock_get.return_value = response

        records = OutlookMailHandler.fetch_graph_emails('child@outlook.com', 'graph-token', folder='junkemail')

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['subject'], 'Your code')
        self.assertEqual(records[0]['sender'], 'OpenAI <noreply@tm.openai.com>')
        self.assertEqual(records[0]['content'], '<p>654321</p>')
        self.assertEqual(records[0]['folder'], 'junkemail')
        url = mock_get.call_args.args[0]
        self.assertEqual(url, 'https://graph.microsoft.com/v1.0/me/mailFolders/junkemail/messages')
        self.assertEqual(mock_get.call_args.kwargs['headers']['Authorization'], 'Bearer graph-token')

    @patch('backend.utils.email.mail_processor.OutlookMailHandler.fetch_graph_emails_from_folders')
    @patch('backend.utils.email.mail_processor.OutlookMailHandler.get_new_graph_access_token')
    @patch('backend.utils.email.mail_processor.OutlookMailHandler.fetch_emails_from_folders')
    @patch('backend.utils.email.mail_processor.OutlookMailHandler.get_new_access_token')
    def test_check_email_task_falls_back_to_graph_when_imap_auth_fails(
        self,
        mock_get_imap_token,
        mock_fetch_imap,
        mock_get_graph_token,
        mock_fetch_graph,
    ):
        class FakeDb:
            def __init__(self):
                self.updated_tokens = []
                self.saved = []
                self.updated_check_times = []

            def update_email_token(self, email_id, token):
                self.updated_tokens.append((email_id, token))

            def get_mail_record_folders(self, email_id):
                return []

            def add_mail_record(self, **kwargs):
                self.saved.append(kwargs)
                return True, len(self.saved)

            def update_check_time(self, email_id):
                self.updated_check_times.append(email_id)

        fake_db = FakeDb()
        processor = EmailBatchProcessor(fake_db, max_workers=1)
        processor.manual_thread_pool.shutdown(wait=False)
        processor.realtime_thread_pool.shutdown(wait=False)

        email_info = {
            'id': 7,
            'email': 'child@outlook.com',
            'mail_type': 'outlook',
            'client_id': 'client-id',
            'refresh_token': 'refresh-token',
            'last_check_time': None,
        }
        graph_records = [{
            'subject': 'OpenAI code',
            'sender': 'noreply@tm.openai.com',
            'received_time': datetime(2026, 5, 30, 1, 2, 3, tzinfo=timezone.utc),
            'content': '<p>123456</p>',
            'folder': 'inbox',
            'mail_key': 'graph-message-id',
        }]
        progress_events = []

        mock_get_imap_token.return_value = 'imap-token'
        mock_fetch_imap.side_effect = OutlookIMAPAuthError('AUTHENTICATE failed')
        mock_get_graph_token.return_value = 'graph-token'
        mock_fetch_graph.return_value = graph_records

        result = processor._check_email_task(
            email_info,
            callback=lambda progress, message, status=None: progress_events.append((progress, message, status))
        )

        self.assertTrue(result['success'])
        self.assertIn('Graph兜底', result['message'])
        self.assertEqual(fake_db.updated_tokens, [(7, 'imap-token'), (7, 'graph-token')])
        self.assertEqual(len(fake_db.saved), 1)
        self.assertEqual(fake_db.saved[0]['subject'], 'OpenAI code')
        mock_fetch_graph.assert_called_once_with(
            'child@outlook.com',
            'graph-token',
            folders=['inbox', 'junkemail'],
            callback=unittest.mock.ANY,
            last_check_time=None,
            folder_last_check_times=unittest.mock.ANY,
        )


if __name__ == '__main__':
    unittest.main()
