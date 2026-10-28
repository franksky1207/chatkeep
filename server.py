"""One stateless WSGI application for local QA and production gunicorn.

Only request memory contains conversation data. No content, URL or traceback logs.
"""
import argparse
import base64
from collections import deque
import json
import os
from pathlib import Path
from queue import Queue, Empty, Full
import re
import socket
from threading import BoundedSemaphore, Event, Lock, Thread
import time
from urllib.parse import urlsplit
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
from chatkeep import ExtractionError, extract_url, validate_url
from word_export import ExportError, filename_for
from conversation_export import export_conversation

ROOT = Path(__file__).parent / 'web'
SLOTS = BoundedSemaphore(max(1, min(2, int(os.environ.get('CHATKEEP_MAX_CONCURRENT', '2')))))
MAX_RESPONSE = 24_000_000  # 16 MB document + base64 and bounded metadata.


class ConversionCancelled(Exception):
    pass


def convert(url, emit):
    validate_url(url)
    last = {}
    def progress(stage, current, total):
        value = int(current * 100 / total) if total else None
        key = value if total else current // 65536
        if last.get(stage) == key:
            return
        last[stage] = key
        detail = '%s / %s' % (current, total) if total else '已接收 %s 位元組' % current
        emit({'stage': stage, 'message': {'fetch': '正在擷取分享頁…',
              'parse': '正在解析對話…', 'word': '正在產生 Word…'}[stage],
              'current': current, 'total': total, 'percent': value, 'detail': detail})
    emit({'stage': 'fetch', 'message': '正在連線取得分享頁…', 'percent': None})
    model = extract_url(url,
        on_fetched=lambda: emit({'stage': 'parse', 'message': '正在解析資料串流…', 'percent': None}),
        on_download_progress=lambda c, t: progress('fetch', c, t),
        on_parse_progress=lambda c, t: progress('parse', c, t))
    warnings = []
    artifact = export_conversation(model, 'share_link', allow_zip=False, strict=False, check=getattr(emit, 'check', None),
                      on_progress=lambda c, t: progress('word', c, t),
                      on_pack=lambda: emit({'stage': 'pack', 'message': '正在封裝文件…', 'percent': None}),
                      warnings_out=warnings)
    data = artifact['data']
    model['report']['export'] = artifact['report']
    model['report']['rendering_status'] = 'partial' if warnings else 'rendered'
    if warnings:
        model['report']['rendering_warnings'] = warnings
        model['report']['warnings'].append('閱讀版有 %d 項格式或媒體限制，文件內已註記。' % len(warnings))
    emit({'stage': 'done', 'message': 'Word 已產生，請先查看完整性報告。',
          'report': model['report'], 'filename': filename_for(model['title']),
          'api_version': 1, 'artifact_type': 'docx', 'mime_type': artifact['mime_type'],
          'document': base64.b64encode(data).decode('ascii')})


class RateLimit:
    """Bounded anonymous admission, no URLs/content or forwarded-IP trust."""
    def __init__(self):
        self.lock, self.clients, self.global_requests = Lock(), {}, deque()
    def admit(self, address):
        now = time.monotonic()
        with self.lock:
            for key in list(self.clients):
                if not self.clients[key] or now - self.clients[key][-1] >= 60:
                    del self.clients[key]
            if address not in self.clients and len(self.clients) >= 1024:
                return False
            history = self.clients.setdefault(address, deque())
            for queue in (history, self.global_requests):
                while queue and now - queue[0] >= 60:
                    queue.popleft()
            if len(history) >= 10 or len(self.global_requests) >= 60 or len(self.clients) > 1024:
                return False
            history.append(now); self.global_requests.append(now)
            return True


def valid_host(host):
    try:
        if not host or len(host) > 260 or not re.fullmatch(r'[A-Za-z0-9.\-:\[\]]+', host):
            return False
        parsed = urlsplit('http://' + host)
        parsed.port  # Reject malformed ports as well as malformed IPv6.
        allowed = {'localhost', '127.0.0.1', '::1'}
        allowed.update(x.strip().lower() for x in os.environ.get('CHATKEEP_ALLOWED_HOSTS', '').split(',') if x.strip())
        platform_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
        if platform_host:
            allowed.add(platform_host.lower())
        return parsed.hostname in allowed
    except ValueError:
        return False


HEADERS = [('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
           ('Referrer-Policy', 'no-referrer'),
           ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")]


class Application:
    def __init__(self):
        self.rates = RateLimit()

    def __call__(self, env, start_response):
        def response(code, value, content_type='application/json; charset=utf-8'):
            if not isinstance(value, bytes):
                value = json.dumps({'error': value}, ensure_ascii=False).encode()
            start_response(code, HEADERS + [('Content-Type', content_type), ('Content-Length', str(len(value)))])
            return [value]
        host = env.get('HTTP_HOST', '')
        if not valid_host(host):
            if env.get('PATH_INFO') in ('/api/convert-json', '/api/convert-v2', '/api/convert-chunk-v1', '/api/share-reader-v1'):
                if env.get('REQUEST_METHOD') == 'OPTIONS':
                    from api_origin import preflight_diagnostic
                    start_response('403 Forbidden', HEADERS + preflight_diagnostic('HOST_FORBIDDEN') + [('Content-Length', '0')])
                    return [b'']
                return response('403 Forbidden', json.dumps({'ok': False, 'error': {
                    'code': 'HOST_FORBIDDEN', 'message': '主機不在允許清單。'}}, ensure_ascii=False).encode())
            return response('403 Forbidden', '主機不在允許清單。')
        method, path = env.get('REQUEST_METHOD'), env.get('PATH_INFO')
        if path in ('/api/convert-json', '/api/convert-v2', '/api/convert-chunk-v1', '/api/share-reader-v1'):
            from api_origin import cors_headers, preflight_denial, preflight_diagnostic
            api_headers = HEADERS + cors_headers(env)
            if method == 'OPTIONS':
                denial = preflight_denial(env)
                accepted = denial is None
                code = '204 No Content' if accepted else '403 Forbidden'
                extra = [('Access-Control-Allow-Methods', 'POST'),
                         ('Access-Control-Allow-Headers', 'Content-Type'),
                         ('Access-Control-Max-Age', '600'),
                         ('X-ChatKeep-Preflight', 'ACCEPTED')] if accepted else preflight_diagnostic(denial)
                start_response(code, api_headers + extra + [('Content-Length', '0')])
                return [b'']
            from json_api import handle
            return handle(env, start_response, api_headers, SLOTS, self.rates, mode='share_reader' if path == '/api/share-reader-v1' else 'share' if path == '/api/convert-v2' else 'chunk' if path == '/api/convert-chunk-v1' else 'official')
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if method == 'GET':
            if path in files:
                filename, mime = files[path]
                return response('200 OK', (ROOT / filename).read_bytes(), mime)
            return response('404 Not Found', '找不到下載或頁面，請重新轉換。')
        if path != '/api/convert':
            return response('404 Not Found', '找不到轉換路徑。')
        if method != 'POST':
            return response('405 Method Not Allowed', '請使用轉換表單。')
        origin = env.get('HTTP_ORIGIN')
        try:
            parsed_origin = urlsplit(origin) if origin else None
            if (env.get('CONTENT_TYPE') != 'application/json' or env.get('HTTP_TRANSFER_ENCODING')
                or env.get('HTTP_SEC_FETCH_SITE') == 'cross-site'
                or (parsed_origin and (parsed_origin.scheme not in ('http', 'https') or parsed_origin.netloc != host))):
                return response('403 Forbidden', '請求來源或格式不符。')
            size = int(env.get('CONTENT_LENGTH') or 0)
            if not 0 < size <= 4096:
                return response('413 Content Too Large', '請求超過大小限制。')
            body = env['wsgi.input'].read(size)
            if len(body) != size:
                raise ValueError()
            payload = json.loads(body)
            url = payload['url']
            validate_url(url)
        except (ValueError, KeyError, TypeError, RecursionError, socket.timeout):
            return response('400 Bad Request', '請輸入有效的公開 ChatGPT 分享連結。')
        if not self.rates.admit(env.get('REMOTE_ADDR', 'unknown')):
            return response('429 Too Many Requests', '請求過於頻繁，請稍後再試。')
        if not SLOTS.acquire(blocking=False):
            return response('429 Too Many Requests', '目前轉換中，請稍後再試。')
        start_response('200 OK', HEADERS + [('Content-Type', 'application/x-ndjson; charset=utf-8'),
                                          ('X-Accel-Buffering', 'no')])
        return self.stream(url)

    def stream(self, url):
        queue, stopped = Queue(maxsize=8), Event()
        deadline = time.monotonic() + 85
        def emit(event):
            encoded = (json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n').encode()
            if len(encoded) > MAX_RESPONSE:
                raise ExportError('轉換回應超過安全大小限制，未提供截斷文件。')
            while not stopped.is_set():
                if time.monotonic() > deadline:
                    raise ConversionCancelled()
                try:
                    queue.put(encoded, timeout=.2)
                    return
                except Full:
                    continue
            raise ConversionCancelled()
        def check():
            if stopped.is_set() or time.monotonic() > deadline:
                raise ConversionCancelled()
        emit.check = check
        def worker():
            try:
                convert(url, emit)
            except ConversionCancelled:
                pass
            except (ExtractionError, ExportError) as exc:
                try: emit({'stage': 'error', 'message': str(exc), 'code': getattr(exc, 'code', 'EXTRACTION_FAILED')})
                except ConversionCancelled: pass
            except Exception:
                try: emit({'stage': 'error', 'message': '轉換失敗，未產生可驗證文件。請稍後重試。'})
                except ConversionCancelled: pass
            finally:
                stopped.set()
                SLOTS.release()
        thread = Thread(target=worker, daemon=True)
        thread.start()
        try:
            while not stopped.is_set() or not queue.empty():
                if time.monotonic() > deadline:
                    yield (json.dumps({'stage': 'error', 'message': '轉換逾時，請稍後重試。'}, ensure_ascii=False) + '\n').encode()
                    break
                try:
                    yield queue.get(timeout=1)
                except Empty:
                    yield b'\n'  # Transport heartbeat, no fabricated progress.
        finally:
            stopped.set()  # Producer exits at its next real progress callback.
            # Do not release its slot until the actual work has stopped.


application = Application()


class Handler(WSGIRequestHandler):
    def setup(self):
        super().setup(); self.connection.settimeout(10)
    def log_message(self, *args):
        pass


class Server(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    def __init__(self, address, handler=Handler):
        self.request_slots = BoundedSemaphore(8)
        super().__init__(address, handler)
        self.set_app(Application())
    def process_request(self, request, address):
        if not self.request_slots.acquire(blocking=False):
            request.close(); return
        super().process_request(request, address)
    def process_request_thread(self, request, address):
        try: super().process_request_thread(request, address)
        finally: self.request_slots.release()
    def handle_error(self, request, client_address):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ChatKeep 本機測試網站')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8000, type=int)
    args = parser.parse_args()
    with Server((args.host, args.port), Handler) as server:
        print('ChatKeep 本機網址：http://%s:%d' % (args.host, args.port), flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass
