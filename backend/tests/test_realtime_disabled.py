import sys
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


class RealtimeDisabledApiTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('backend.app.email_processor.start_real_time_check')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_start_realtime_endpoint_is_disabled_to_prevent_429(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_start,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'tester', 'is_admin': False}

        response = self.client.post(
            '/api/email/start_real_time_check',
            json={'check_interval': 60},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 410)
        self.assertIn('\u5df2\u5173\u95ed', response.get_json()['message'])
        mock_start.assert_not_called()

    @patch('backend.app.email_processor.add_to_real_time_queue', create=True)
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_realtime_queue_endpoint_is_disabled_to_keep_manual_only(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_add_to_queue,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'tester', 'is_admin': False}

        response = self.client.post(
            '/api/email/add_to_real_time_queue',
            json={'email_id': 1},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 410)
        self.assertIn('\u5df2\u5173\u95ed', response.get_json()['message'])
        mock_add_to_queue.assert_not_called()

    @patch('backend.app.db.set_email_realtime_check')
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_enable_single_email_realtime_toggle_is_rejected(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_get_email_by_id,
        mock_set_realtime,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'tester', 'is_admin': False}
        mock_get_email_by_id.return_value = {'id': 7, 'user_id': 99, 'email': 'manual-only@outlook.com'}

        response = self.client.post(
            '/api/emails/7/realtime',
            json={'enable': True},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 410)
        self.assertIn('\u5df2\u5173\u95ed', response.get_json()['message'])
        mock_set_realtime.assert_not_called()

    @patch('backend.app.db.set_email_realtime_check')
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_disable_single_email_realtime_toggle_remains_allowed_for_old_data(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_get_email_by_id,
        mock_set_realtime,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'tester', 'is_admin': False}
        mock_get_email_by_id.return_value = {'id': 7, 'user_id': 99, 'email': 'manual-only@outlook.com'}
        mock_set_realtime.return_value = True

        response = self.client.post(
            '/api/emails/7/realtime',
            json={'enable': False},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['data']['enable_realtime_check'])
        mock_set_realtime.assert_called_once_with(7, False)

    @patch('backend.app.email_processor.stop_real_time_check')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_stop_realtime_endpoint_accepts_authenticated_user_for_compatibility(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_stop,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'tester', 'is_admin': False}
        mock_stop.return_value = False

        response = self.client.post(
            '/api/email/stop_real_time_check',
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()['success'])
        mock_stop.assert_called_once_with()

    def test_mail_processor_realtime_starter_is_noop(self):
        from backend.utils.email.mail_processor import EmailBatchProcessor

        processor = EmailBatchProcessor(db=object(), max_workers=1)
        try:
            result = processor.start_real_time_check(check_interval=30)

            self.assertFalse(result)
            self.assertFalse(processor.real_time_checker.running)
            self.assertIsNone(processor.real_time_checker.thread)
        finally:
            processor.manual_thread_pool.shutdown(wait=False)
            processor.realtime_thread_pool.shutdown(wait=False)


if __name__ == '__main__':
    unittest.main()
