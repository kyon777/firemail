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


class RegisterMailPoolGateTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    @patch('backend.app.db.create_user')
    @patch('backend.app.db.is_registration_allowed')
    def test_register_requires_internal_pool_email(self, mock_allowed, mock_create_user):
        mock_allowed.return_value = True

        response = self.client.post(
            '/api/auth/register',
            json={'username': 'customer', 'password': 'zz123456'}
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()['error'], '注册验证邮箱不能为空')
        mock_create_user.assert_not_called()

    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.create_user')
    @patch('backend.app.db.is_registration_allowed')
    def test_register_rejects_email_not_in_internal_pool(
        self,
        mock_allowed,
        mock_create_user,
        mock_cache,
    ):
        mock_allowed.return_value = True
        mock_cache.get.return_value = None

        response = self.client.post(
            '/api/auth/register',
            json={
                'username': 'customer',
                'password': 'zz123456',
                'verification_email': 'missing@outlook.com'
            }
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], '验证邮箱不在可注册邮箱库中')
        mock_cache.get.assert_called_once_with('missing@outlook.com')
        mock_create_user.assert_not_called()

    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.create_user')
    @patch('backend.app.db.is_registration_allowed')
    def test_register_rejects_disabled_pool_email(
        self,
        mock_allowed,
        mock_create_user,
        mock_cache,
    ):
        mock_allowed.return_value = True
        mock_cache.get.return_value = {'email': 'disabled@outlook.com', 'status': 'disabled'}

        response = self.client.post(
            '/api/auth/register',
            json={
                'username': 'customer',
                'password': 'zz123456',
                'verification_email': 'disabled@outlook.com'
            }
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['error'], '验证邮箱已停用，不能用于注册')
        mock_create_user.assert_not_called()

    @patch('backend.app.mail_pool_cache')
    @patch('backend.app.db.create_user')
    @patch('backend.app.db.is_registration_allowed')
    def test_register_accepts_pool_email_without_exposing_credentials(
        self,
        mock_allowed,
        mock_create_user,
        mock_cache,
    ):
        mock_allowed.return_value = True
        mock_cache.get.return_value = {
            'email': 'customer@outlook.com',
            'password': 'secret-password',
            'client_id': 'client-id',
            'refresh_token': 'refresh-token',
            'status': 'assigned',
        }
        mock_create_user.return_value = (True, False)

        response = self.client.post(
            '/api/auth/register',
            json={
                'username': 'customer',
                'password': 'zz123456',
                'verification_email': '  Customer@Outlook.com  '
            }
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['message'], '注册成功')
        self.assertEqual(body['username'], 'customer')
        self.assertNotIn('secret-password', str(body))
        self.assertNotIn('refresh-token', str(body))
        mock_cache.get.assert_called_once_with('customer@outlook.com')
        mock_create_user.assert_called_once_with('customer', 'zz123456')


if __name__ == '__main__':
    unittest.main()
