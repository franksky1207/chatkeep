"""Synthetic WSGI origin admission, preflight and real converter regression."""
from io import BytesIO
import json
import os
import unittest
from unittest.mock import patch
from server import Application
from test_official_json import body

PAGES = 'https://franksky1207.github.io'


class PagesCorsTests(unittest.TestCase):
    def call(self, **changes):
        raw = body()
        env = dict(HTTP_HOST='localhost', PATH_INFO='/api/convert-json', REQUEST_METHOD='POST',
                   CONTENT_TYPE='application/json', CONTENT_LENGTH=str(len(raw)),
                   HTTP_ORIGIN=PAGES, HTTP_SEC_FETCH_SITE='cross-site',
                   REMOTE_ADDR='127.0.0.1', **{'wsgi.input': BytesIO(raw), 'wsgi.url_scheme': 'http'})
        env.update(changes)
        captured = []
        with patch.dict(os.environ, {'CHATKEEP_ALLOWED_ORIGINS': PAGES + ',http://localhost:9000'}):
            result = b''.join(Application()(env, lambda s, h: captured.append((s, dict(h)))))
        return int(captured[0][0].split()[0]), captured[0][1], json.loads(result) if result else None

    def test_options_all_new_routes(self):
        for path in ['/api/convert-v2', '/api/convert-json', '/api/convert-chunk-v1']:
            status, headers, value = self.call(PATH_INFO=path, REQUEST_METHOD='OPTIONS',
                HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST', HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type')
            self.assertEqual(status, 204)
            self.assertEqual(headers['Access-Control-Allow-Origin'], PAGES)
            self.assertEqual(headers['Access-Control-Allow-Methods'], 'POST')
            self.assertEqual(headers['Access-Control-Allow-Headers'], 'Content-Type')
            self.assertNotIn('Access-Control-Allow-Credentials', headers)
            self.assertIsNone(value)

    def test_preflight_denials(self):
        for changes in [dict(HTTP_ORIGIN='https://evil.test'), dict(HTTP_ORIGIN='null'),
                        dict(HTTP_ORIGIN=PAGES+'/path'), dict(HTTP_ORIGIN='https://franksky1207.github.io.evil.test'),
                        dict(HTTP_ACCESS_CONTROL_REQUEST_HEADERS='Authorization'),
                        dict(HTTP_ACCESS_CONTROL_REQUEST_METHOD='DELETE'), dict(HTTP_COOKIE='secret')]:
            args = dict(REQUEST_METHOD='OPTIONS', HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                        HTTP_ACCESS_CONTROL_REQUEST_HEADERS='Content-Type')
            args.update(changes)
            self.assertEqual(self.call(**args)[0], 403)

    def test_real_cross_site_converter_and_exposed_retry(self):
        status, headers, value = self.call()
        self.assertEqual(status, 200)
        self.assertEqual(headers['Access-Control-Allow-Origin'], PAGES)
        self.assertEqual(headers['Access-Control-Expose-Headers'], 'Retry-After')
        self.assertEqual(headers['Vary'], 'Origin')
        self.assertEqual(value['api_version'], 2)
        self.assertIn('file_sha256', value['report']['volumes'][0])
        self.assertEqual(self.call(HTTP_ORIGIN='http://localhost:9000')[0], 200)

    def test_actual_denials_and_preserved_host_content_limits(self):
        for args in [dict(HTTP_ORIGIN='https://evil.test'), dict(HTTP_ORIGIN=''),
                     dict(HTTP_COOKIE='secret'), dict(HTTP_AUTHORIZATION='Bearer secret'),
                     dict(HTTP_HOST='evil.test')]:
            self.assertEqual(self.call(**args)[0], 403)
        self.assertEqual(self.call(CONTENT_TYPE='text/plain')[0], 415)
        self.assertEqual(self.call(CONTENT_LENGTH='2000001')[0], 413)
        with patch.dict(os.environ, {'CHATKEEP_ALLOWED_ORIGINS': ''}):
            from api_origin import allowed_origin
            self.assertFalse(allowed_origin({'HTTP_ORIGIN':PAGES, 'HTTP_HOST':'localhost'}))
            self.assertTrue(allowed_origin({'HTTP_ORIGIN':'http://localhost', 'HTTP_HOST':'localhost'}))

    def test_allowed_error_response_and_preflight_keep_limits(self):
        with patch('server.RateLimit.admit', return_value=False) as admit:
            status, headers, value = self.call()
            self.assertEqual(status, 429)
            self.assertEqual(headers['Retry-After'], '60')
            self.assertEqual(headers['Access-Control-Allow-Origin'], PAGES)
            self.assertEqual(value['error']['code'], 'RATE_LIMITED')
            admit.reset_mock()
            self.assertEqual(self.call(REQUEST_METHOD='OPTIONS', HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST')[0], 204)
            admit.assert_not_called()
            self.assertEqual(self.call(HTTP_ORIGIN='https://evil.test')[0], 403)
            admit.assert_not_called()
