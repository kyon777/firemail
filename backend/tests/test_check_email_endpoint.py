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

from backend.app import app


class CheckEmailEndpointTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('backend.app.email_processor.manual_thread_pool.submit')
    @patch('backend.app.email_processor.is_email_being_processed')
    @patch('backend.app.db.get_email_by_id')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_check_email_returns_immediately_after_scheduling(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_get_email_by_id,
        mock_processing,
        mock_submit,
    ):
        current_user = {'id': 99, 'username': 'tester', 'is_admin': False}
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = current_user
        mock_get_email_by_id.return_value = {'id': 1, 'user_id': 99, 'email': 'demo@outlook.com'}
        mock_processing.return_value = False

        mock_future = MagicMock()
        mock_future.result.return_value = {
            'success': True,
            'status': 'completed',
            'message': 'task finished'
        }
        mock_submit.return_value = mock_future

        response = self.client.post(
            '/api/emails/1/check',
            json={},
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertIn(response.status_code, (200, 202))
        data = response.get_json()
        self.assertEqual(data['status'], 'started')
        self.assertIn('message', data)
        mock_submit.assert_called_once()
        mock_future.result.assert_not_called()


if __name__ == '__main__':
    unittest.main()
