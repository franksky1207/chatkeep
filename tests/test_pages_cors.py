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
                        dict(HTTP_ORIGIN=PAGES+'/'),
                        dict(HTTP_ACCESS_CONTROL_REQUEST_HEADERS='Authorization'),
                        dict(HTTP_ACCESS_CONTROL_REQUEST_METHOD='DELETE'), dict(HTTP_COOKIE='secret')]:
            args = dict(REQUEST_METHOD='OPTIONS', HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                        HTTP_ACCESS_CONTROL_REQUEST_HEADERS='Content-Type')
            args.update(changes)
            self.assertEqual(self.call(**args)[0], 403)

    def test_precise_private_preflight_diagnostics(self):
        cases = [
            ({'HTTP_HOST':'private.invalid'}, 'HOST_FORBIDDEN'),
            ({'HTTP_ORIGIN':'https://private.invalid'}, 'ORIGIN_FORBIDDEN'),
            ({'HTTP_ACCESS_CONTROL_REQUEST_METHOD':'DELETE'}, 'PREFLIGHT_METHOD_FORBIDDEN'),
            ({'HTTP_ACCESS_CONTROL_REQUEST_HEADERS':'x-private-header'}, 'PREFLIGHT_HEADERS_FORBIDDEN'),
            ({'HTTP_COOKIE':'PRIVATE_COOKIE'}, 'PREFLIGHT_CREDENTIALS_FORBIDDEN'),
            ({'HTTP_AUTHORIZATION':'PRIVATE_AUTH'}, 'PREFLIGHT_CREDENTIALS_FORBIDDEN')]
        for changes, code in cases:
            args = dict(REQUEST_METHOD='OPTIONS', HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                        HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type', QUERY_STRING='PRIVATE_QUERY')
            args.update(changes)
            with self.assertLogs('chatkeep.cors', level='WARNING') as logs:
                status, headers, value = self.call(**args)
            self.assertEqual(status, 403)
            self.assertEqual(headers['X-ChatKeep-Preflight'], code)
            self.assertEqual(logs.records[0].getMessage(), 'chatkeep_preflight_denied status=403 code='+code)
            self.assertEqual(len(logs.records), 1)
            self.assertIsNone(value)
            if code in ('HOST_FORBIDDEN', 'ORIGIN_FORBIDDEN'):
                self.assertNotIn('Access-Control-Allow-Origin', headers)
            else:
                self.assertEqual(headers['Access-Control-Allow-Origin'], PAGES)
            self.assertNotIn('Access-Control-Allow-Credentials', headers)

    def test_render_https_termination_and_webkit_headers(self):
        # Explicit Pages allowlist must work despite internal HTTP. Never trust
        # client-supplied forwarded protocol/host to admit a different origin.
        with patch.dict(os.environ, {'RENDER_EXTERNAL_HOSTNAME':'chatkeep.onrender.com'}):
            for requested in ['', 'content-type', 'Content-Type', ' content-type ']:
                status, headers, _ = self.call(HTTP_HOST='chatkeep.onrender.com',
                    REQUEST_METHOD='OPTIONS', HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
                    HTTP_ACCESS_CONTROL_REQUEST_HEADERS=requested,
                    HTTP_ACCEPT='*/*', HTTP_ACCEPT_LANGUAGE='zh-TW,zh-Hant;q=0.9',
                    HTTP_USER_AGENT='Synthetic WebKit', HTTP_SEC_FETCH_MODE='cors',
                    HTTP_SEC_FETCH_DEST='empty', HTTP_X_FORWARDED_PROTO='https')
                self.assertEqual(status, 204)
                self.assertEqual(headers['X-ChatKeep-Preflight'], 'ACCEPTED')
                self.assertEqual(headers['Access-Control-Allow-Origin'], PAGES)
            self.assertEqual(self.call(HTTP_HOST='chatkeep.onrender.com')[0], 200)
            self.assertEqual(self.call(HTTP_ORIGIN='https://evil.test',
                HTTP_X_FORWARDED_PROTO='https', HTTP_X_FORWARDED_HOST='evil.test')[0], 403)
            self.assertEqual(self.call(HTTP_HOST='evil.test', HTTP_X_FORWARDED_HOST='chatkeep.onrender.com')[0], 403)

    def test_missing_or_malformed_environment_fails_closed(self):
        from api_origin import preflight_denial
        env = dict(HTTP_HOST='chatkeep.onrender.com', HTTP_ORIGIN=PAGES,
                   HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST', HTTP_ACCESS_CONTROL_REQUEST_HEADERS='content-type')
        for configured in ['', PAGES+'/', PAGES+'/chatkeep/', 'https://other.invalid']:
            with patch.dict(os.environ, {'CHATKEEP_ALLOWED_ORIGINS':configured}):
                self.assertEqual(preflight_denial(env), 'ORIGIN_FORBIDDEN')
        with patch.dict(os.environ, {'CHATKEEP_ALLOWED_ORIGINS':PAGES}):
            self.assertIsNone(preflight_denial(env))

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
