import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import remote_model
from demo import context_demo_messages


class RemoteModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_config = dict(remote_model.CONFIG)
        self.old_path = remote_model.CONFIG_PATH
        remote_model.CONFIG_PATH = Path(self.tmp.name) / 'model-config.json'
        remote_model.CONFIG.update(base_url='https://api.deepseek.com', model='test-model', api_key='test-only-key')
        self.rows = context_demo_messages()

    def tearDown(self):
        remote_model.CONFIG.clear()
        remote_model.CONFIG.update(self.old_config)
        remote_model.CONFIG_PATH = self.old_path
        self.tmp.cleanup()

    def event(self):
        target = self.rows[5]
        return {'kind': 'fact', 'event': 'confirmation', 'title': '演示改为10月22日，待核对',
                'subject': '我', 'due': '2026-10-22', 'evidence': [
                    {'id': target['id'], 'quote': target['text']},
                    {'id': self.rows[4]['id'], 'quote': self.rows[4]['text']}]}

    def response(self):
        return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps({'events': [self.event()]}, ensure_ascii=False)}}]}).encode())

    def test_custom_model_and_non_secret_persistence(self):
        status = remote_model.configure('https://api.deepseek.com', 'my/model:v2', 'test-new-key')
        self.assertEqual(status['model'], 'my/model:v2')
        self.assertTrue(status['has_key'])
        self.assertNotIn('api_key', status)
        saved = remote_model.CONFIG_PATH.read_text('utf-8')
        self.assertNotIn('test-new-key', saved)

    def test_endpoint_change_clears_old_key(self):
        status = remote_model.configure('https://other.example/v1', 'custom-model')
        self.assertFalse(status['has_key'])
        self.assertEqual(remote_model.CONFIG['api_key'], '')

    def test_insecure_external_url_and_embedded_key_rejected(self):
        for endpoint in ('http://external.example/v1', 'https://user:key@example.com', 'https://example.com?key=test'):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                remote_model.configure(endpoint, 'test-model')

    def test_real_or_spoofed_messages_blocked_before_request(self):
        target = {**self.rows[5], 'text': '这是模拟私有内容，与内置合成源不同'}
        with patch('remote_model.build_opener') as mocked, self.assertRaises(ValueError):
            remote_model.extract_demo(target, self.rows[:5])
        mocked.assert_not_called()

    def test_response_and_request_contract(self):
        with patch('remote_model.build_opener') as mocked:
            mocked.return_value.open.return_value = self.response()
            result = remote_model.extract_demo(self.rows[5], self.rows[:5])
            request = mocked.return_value.open.call_args.args[0]
            data = json.loads(request.data)
            self.assertEqual(request.full_url, 'https://api.deepseek.com/chat/completions')
            self.assertEqual(data['model'], 'test-model')
            self.assertEqual(data['response_format'], {'type': 'json_object'})
            self.assertEqual(data['thinking'], {'type': 'disabled'})
            self.assertEqual(result[0]['due'], '2026-10-22')
            self.assertEqual(set(result[0]['evidence_ids']), {'ctx-05', 'ctx-06'})

    def test_http_error_does_not_echo_secret_or_response(self):
        with patch('remote_model.build_opener') as mocked:
            mocked.return_value.open.side_effect = HTTPError('https://example.com', 401, 'test-only-key', {}, None)
            with self.assertRaises(ValueError) as error:
                remote_model.extract_demo(self.rows[5], self.rows[:5])
        self.assertIn('401', str(error.exception))
        self.assertNotIn('test-only-key', str(error.exception))

    def test_no_key_does_not_send_request(self):
        remote_model.CONFIG['api_key'] = ''
        with patch('remote_model.build_opener') as mocked, self.assertRaises(ValueError):
            remote_model.extract_demo(self.rows[5], self.rows[:5])
        mocked.assert_not_called()

    def test_redirect_is_disabled(self):
        with self.assertRaises(ValueError):
            remote_model.NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_invalid_key_is_rejected_without_echo(self):
        for key in ('test\x00secret', 'test\nsecret', '含中文的密钥'):
            with self.subTest(key_length=len(key)), self.assertRaises(ValueError) as error:
                remote_model.configure('https://api.deepseek.com', 'test-model', key)
            self.assertNotIn(key, str(error.exception))


if __name__ == '__main__':
    unittest.main()
