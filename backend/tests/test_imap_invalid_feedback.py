import sys
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

from backend.utils.email.imap import IMAPMailboxInvalidError, IMAPMailHandler
from backend.utils.email.mail_processor import EmailBatchProcessor


class IMAPInvalidFeedbackTestCase(unittest.TestCase):
    def test_fetch_emails_raises_invalid_error_when_login_fails(self):
        fake_mail = MagicMock()
        fake_mail.login.side_effect = Exception('AUTHENTICATIONFAILED invalid credentials')

        with patch('backend.utils.email.imap.imaplib.IMAP4_SSL', return_value=fake_mail):
            with self.assertRaises(IMAPMailboxInvalidError):
                IMAPMailHandler.fetch_emails(
                    'bad@example.com',
                    'wrong-password',
                    server='imap.example.com',
                    port=993,
                    use_ssl=True,
                )

    def test_check_email_task_reports_invalid_status_to_progress_callback(self):
        processor = EmailBatchProcessor(MagicMock(), max_workers=1)
        self.addCleanup(processor.manual_thread_pool.shutdown, False)
        self.addCleanup(processor.realtime_thread_pool.shutdown, False)

        callback_events = []

        with patch(
            'backend.utils.email.mail_processor.IMAPMailHandler.fetch_emails',
            side_effect=IMAPMailboxInvalidError('AUTHENTICATIONFAILED invalid credentials')
        ):
            result = processor._check_email_task({
                'id': 88,
                'email': 'bad@example.com',
                'password': 'wrong-password',
                'mail_type': 'imap',
                'server': 'imap.example.com',
                'port': 993,
                'use_ssl': True,
                'last_check_time': None,
            }, lambda progress, message, status=None: callback_events.append((progress, message, status)))

        self.assertFalse(result['success'])
        self.assertEqual(result['status'], 'invalid')
        self.assertTrue(callback_events)
        self.assertEqual(callback_events[-1][0], 100)
        self.assertEqual(callback_events[-1][2], 'invalid')


if __name__ == '__main__':
    unittest.main()
