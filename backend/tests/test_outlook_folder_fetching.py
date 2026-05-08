import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend.utils.email.common import normalize_check_time
from backend.utils.email.mail_processor import EmailBatchProcessor, MailProcessor
from backend.utils.email.outlook import OutlookMailHandler


class FakeOutlookIMAP:
    def __init__(self, *args, **kwargs):
        self.selected_folders = []

    def authenticate(self, mechanism, callback):
        callback(None)
        return 'OK', []

    def list(self):
        return 'OK', [
            b'(\\Marked \\HasNoChildren) "/" Inbox',
            b'(\\Marked \\HasNoChildren \\Junk) "/" Junk'
        ]

    def select(self, folder):
        self.selected_folders.append(folder)
        return 'OK', [b'1']

    def search(self, charset, criteria):
        return 'OK', [b'1']

    def fetch(self, mail_id, parts):
        raw_message = (
            b"Subject: Spam notice\r\n"
            b"From: sender@example.com\r\n"
            b"Date: Fri, 08 May 2026 10:00:00 +0000\r\n"
            b"Content-Type: text/plain; charset=utf-8\r\n"
            b"\r\n"
            b"hello"
        )
        return 'OK', [(b'1 (RFC822 {0})', raw_message)]

    def logout(self):
        return 'BYE', []


class OutlookFolderFetchingTestCase(unittest.TestCase):
    @patch('backend.utils.email.outlook.imaplib.IMAP4_SSL', return_value=FakeOutlookIMAP())
    def test_fetch_emails_uses_requested_folder_and_preserves_folder_name(self, mock_imap):
        records = OutlookMailHandler.fetch_emails(
            'demo@outlook.com',
            'access-token',
            folder='junkemail',
            callback=lambda progress, folder: None,
            last_check_time=None
        )

        imap_instance = mock_imap.return_value
        self.assertEqual(['Junk'], imap_instance.selected_folders)
        self.assertEqual(1, len(records))
        self.assertEqual('Junk', records[0]['folder'])

    @patch('backend.utils.email.mail_processor.OutlookMailHandler.fetch_emails_from_folders', create=True)
    @patch('backend.utils.email.mail_processor.OutlookMailHandler.get_new_access_token')
    def test_check_email_task_fetches_inbox_and_junk_for_outlook_and_backfills_new_folder(
        self,
        mock_get_new_access_token,
        mock_fetch_emails_from_folders,
    ):
        db = MagicMock()
        db.get_mail_record_folders.return_value = ['INBOX']

        processor = EmailBatchProcessor(db, max_workers=1)
        self.addCleanup(processor.manual_thread_pool.shutdown, False)
        self.addCleanup(processor.realtime_thread_pool.shutdown, False)

        mock_get_new_access_token.return_value = 'fresh-access-token'
        mock_fetch_emails_from_folders.return_value = [
            {
                'subject': 'Inbox mail',
                'sender': 'inbox@example.com',
                'received_time': datetime(2026, 5, 8, 10, 0, 0),
                'content': 'inbox',
                'folder': 'inbox',
                'mail_key': 'inbox-mail',
            },
            {
                'subject': 'Junk mail',
                'sender': 'junk@example.com',
                'received_time': datetime(2026, 5, 7, 10, 0, 0),
                'content': 'junk',
                'folder': 'junkemail',
                'mail_key': 'junk-mail',
            }
        ]
        processor.save_mail_records = MagicMock(return_value=2)
        processor.update_check_time = MagicMock(return_value=True)

        email_info = {
            'id': 20,
            'email': 'VincentYoung4050@outlook.com',
            'mail_type': 'outlook',
            'refresh_token': 'refresh-token',
            'client_id': 'client-id',
            'last_check_time': '2026-05-08 07:59:40',
        }

        result = processor._check_email_task(email_info)

        self.assertTrue(result['success'])
        mock_fetch_emails_from_folders.assert_called_once()
        args, kwargs = mock_fetch_emails_from_folders.call_args
        self.assertEqual('VincentYoung4050@outlook.com', args[0])
        self.assertEqual('fresh-access-token', args[1])
        self.assertEqual(['inbox', 'junkemail'], kwargs['folders'])
        self.assertEqual(
            normalize_check_time('2026-05-08 07:59:40'),
            kwargs['folder_last_check_times']['inbox']
        )
        self.assertIsNone(kwargs['folder_last_check_times']['junkemail'])
        processor.save_mail_records.assert_called_once_with(db, 20, mock_fetch_emails_from_folders.return_value, None)

    def test_save_mail_records_does_not_merge_same_subject_sender_with_different_times(self):
        db = MagicMock()
        db.add_mail_record.side_effect = [(True, 1), (True, 2)]

        mail_records = [
            {
                'subject': 'Verification code',
                'sender': 'no-reply@microsoft.com',
                'received_time': datetime(2026, 5, 8, 10, 0, 0),
                'content': 'first',
                'folder': 'inbox',
            },
            {
                'subject': 'Verification code',
                'sender': 'no-reply@microsoft.com',
                'received_time': datetime(2026, 5, 8, 10, 5, 0),
                'content': 'second',
                'folder': 'junkemail',
            },
        ]

        saved_count = MailProcessor.save_mail_records(db, 20, mail_records, progress_callback=lambda *_: None)

        self.assertEqual(2, saved_count)
        self.assertEqual(2, db.add_mail_record.call_count)


if __name__ == '__main__':
    unittest.main()
