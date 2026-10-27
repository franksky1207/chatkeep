"""Local-only stateless HTTP adapter. Conversation data lives in request memory."""
import argparse
import base64
import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore
from urllib.parse import urlsplit
from chatkeep import ExtractionError, extract_url, validate_url
from word_export import ExportError, build_docx, filename_for

ROOT = Path(__file__).parent / 'web'
SLOTS = BoundedSemaphore(2)


def convert(url, emit):
    validate_url(url)
    last = {}
    def progress(stage, current, total):
        # Throttle repeated reports, never invent a denominator.
        value = int(current * 100 / total) if total else None
        key = (value, current == total if total else False)
        if last.get(stage) == key:
            return
        last[stage] = key
        detail = ('%s / %s' % (current, total)) if total else ('已接收 %s 位元組' % current)
        emit({'stage': stage, 'message': {
            'fetch': '正在擷取分享頁…',
            'parse': '正在解析對話…',
            'word': '正在產生 Word…'}[stage], 'current': current,
            'total': total, 'percent': value, 'detail': detail})
    emit({'stage': 'fetch', 'message': '正在連線取得分享頁…', 'percent': None})
    model = extract_url(
        url,
        on_fetched=lambda: emit({'stage': 'parse', 'message': '正在解析資料串流…', 'percent': None}),
        on_download_progress=lambda current, total: progress('fetch', current, total),
        on_parse_progress=lambda current, total: progress('parse', current, total))
    emit({'stage': 'parse', 'message': '對話解析完成', 'percent': 100,
          'current': model['report']['raw_nodes'], 'total': model['report']['raw_nodes']})
    emit({'stage': 'word', 'message': '正在排版 Word…', 'percent': None})
    data = build_docx(model, rich=True,
                      on_progress=lambda current, total: progress('word', current, total))
    emit({'stage': 'pack', 'message': '正在準備下載檔案…', 'percent': None})
    emit({'stage': 'done', 'message': 'Word 已產生，請先查看完整性報告。',
          'report': model['report'], 'filename': filename_for(model['title']),
          'document': base64.b64encode(data).decode('ascii')})


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # Never log URLs, request bodies, conversation text or exceptions.

    def send_headers(self, code, content_type):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

    def allowed_host(self):
        try:
            host = urlsplit('http://' + self.headers.get('Host', '')).hostname
            return host in {'localhost', '127.0.0.1', '::1', self.server.server_address[0]}
        except ValueError:
            return False

    def do_GET(self):
        if not self.allowed_host():
            self.send_headers(403, 'text/plain')
            return
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8')}
        asset = files.get(self.path)
        if not asset:
            self.send_headers(404, 'text/plain; charset=utf-8')
            self.wfile.write('找不到下載或頁面，請重新轉換。'.encode())
            return
        self.send_headers(200, asset[1])
        self.wfile.write((ROOT / asset[0]).read_bytes())

    def do_POST(self):
        if not self.allowed_host():
            self.send_headers(403, 'application/json')
            return
        if self.path != '/api/convert':
            self.send_headers(404, 'application/json')
            return
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        # JSON-only and same-origin: browser pages cannot submit cross-site forms.
        if (self.headers.get('Content-Type') != 'application/json'
                or self.headers.get('Transfer-Encoding')
                or (origin and (urlsplit(origin).scheme not in ('http', 'https') or urlsplit(origin).netloc != host))):
            self.send_headers(403, 'application/json')
            self.wfile.write(b'{"error":"request rejected"}')
            return
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                raise ValueError()
            payload = json.loads(self.rfile.read(size))
            url = payload['url']
            if not isinstance(url, str):
                raise ValueError()
            validate_url(url)
        except (ValueError, KeyError, TypeError, socket.timeout):
            self.send_headers(400, 'application/json; charset=utf-8')
            self.wfile.write(json.dumps({'error': '請輸入有效的公開 ChatGPT 分享連結。'}, ensure_ascii=False).encode())
            return
        if not SLOTS.acquire(blocking=False):
            self.send_headers(429, 'application/json; charset=utf-8')
            self.wfile.write(json.dumps({'error': '目前轉換中，請稍後再試。'}, ensure_ascii=False).encode())
            return
        try:
            self.send_headers(200, 'application/x-ndjson; charset=utf-8')
            def emit(event):
                self.wfile.write((json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n').encode())
                self.wfile.flush()
            try:
                convert(url, emit)
            except (ExtractionError, ExportError) as exc:
                emit({'stage': 'error', 'message': str(exc)})
            except (BrokenPipeError, ConnectionResetError, socket.timeout):
                return
            except Exception:
                emit({'stage': 'error', 'message': '轉換失敗，未產生可驗證文件。請稍後重試。'})
        finally:
            SLOTS.release()


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass  # A disconnected/malformed request must never print payload-bearing traces.



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ChatKeep 本機測試網站（非正式部署）')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8000, type=int)
    args = parser.parse_args()
    with Server((args.host, args.port), Handler) as server:
        print('ChatKeep 本機網址：http://%s:%d' % (args.host, args.port), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
