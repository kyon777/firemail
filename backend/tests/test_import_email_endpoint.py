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


class ImportEmailEndpointTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('backend.app.db.add_email')
    @patch('backend.app.db.get_user_by_id')
    @patch('backend.app.jwt.decode')
    def test_import_endpoint_accepts_legacy_outlook_format(
        self,
        mock_jwt_decode,
        mock_get_user_by_id,
        mock_add_email,
    ):
        mock_jwt_decode.return_value = {'user_id': 99}
        mock_get_user_by_id.return_value = {'id': 99, 'username': 'tester', 'is_admin': False}
        mock_add_email.return_value = 1

        response = self.client.post(
            '/api/emails/import',
            json={
                'data': 'demo@outlook.com----x----M.C549_SN1.token-value$$----9e5f94bc-e8a4-4e73-b8be-63364c29d753',
                'mail_type': 'outlook'
            },
            headers={'Authorization': 'Bearer fake-token'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['success'], 1)
        mock_add_email.assert_called_once_with(
            99,
            'demo@outlook.com',
            'x',
            '9e5f94bc-e8a4-4e73-b8be-63364c29d753',
            'M.C549_SN1.token-value$$',
            'outlook'
        )


if __name__ == '__main__':
    unittest.main()
