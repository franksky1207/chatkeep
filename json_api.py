"""Bounded anonymous JSON transport with explicit browser origin policy."""
from http import HTTPStatus
import json
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event, Timer
from api_origin import allowed_origin
from official_json import MAX_INPUT

UPLOAD_TIMEOUT = 10
CONVERSION_TIMEOUT = 45
MAX_RESPONSE = 24_000_000
WORKER = Path(__file__).resolve().with_name('official_worker.py')


def handle(env, start_response, headers, slots, rates, mode='official'):
    def respond(status, value):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        start_response('%d %s' % (status, HTTPStatus(status).phrase), headers + [
            ('Content-Type', 'application/json; charset=utf-8'), ('Content-Length', str(len(body)))] +
            ([('Retry-After', '60' if value.get('error', {}).get('code') == 'RATE_LIMITED' else '2')] if status == 429 else []))
        return [body]

    def error(status, code, message):
        return respond(status, {'ok': False, 'error': {'code': code, 'message': message}})

    if env.get('REQUEST_METHOD') != 'POST':
        return error(405, 'METHOD_NOT_ALLOWED', '請使用 POST。')
    if not allowed_origin(env) or env.get('HTTP_COOKIE') or env.get('HTTP_AUTHORIZATION'):
        return error(403, 'ORIGIN_FORBIDDEN', '請求來源未獲允許或帶有認證資訊。')
    if env.get('CONTENT_TYPE', '').lower() not in ('application/json', 'application/json; charset=utf-8'):
        return error(415, 'UNSUPPORTED_MEDIA_TYPE', '只接受 UTF-8 application/json。')
    if env.get('HTTP_TRANSFER_ENCODING') or env.get('HTTP_CONTENT_ENCODING') or env.get('CONTENT_ENCODING'):
        return error(415, 'UNSUPPORTED_ENCODING', '不接受壓縮或分塊請求。')
    try: size = int(env.get('CONTENT_LENGTH') or 0)
    except (ValueError, TypeError):
        return error(400, 'INVALID_LENGTH', '請求長度無效。')
    limit = 4096 if mode == 'share' else MAX_INPUT
    if not 0 < size <= limit:
        return error(413, 'INPUT_TOO_LARGE', '分享連結請求不得超過 4,096 bytes。' if mode == 'share' else '請提供不超過 2 MB 的單一對話。')
    if not rates.admit(env.get('REMOTE_ADDR', 'unknown')):
        return error(429, 'RATE_LIMITED', '請求過於頻繁，請稍後再試。')
    if not slots.acquire(blocking=False):
        return error(429, 'BUSY', '目前轉換中，請稍後再試。')
    process = None
    try:
        expired = Event()
        connection = env.get('gunicorn.socket')
        def abort_upload():
            expired.set()
            try: connection.shutdown(socket.SHUT_RD)
            except OSError: pass
        timer = Timer(UPLOAD_TIMEOUT, abort_upload) if connection is not None else None
        if timer:
            timer.daemon = True
            timer.start()
        try:
            body = env['wsgi.input'].read(size)
        except (socket.timeout, TimeoutError):
            return error(408, 'UPLOAD_TIMEOUT', '接收 JSON 逾時。')
        except OSError:
            return error(408 if expired.is_set() else 400,
                         'UPLOAD_TIMEOUT' if expired.is_set() else 'INCOMPLETE_BODY', '接收 JSON 失敗。')
        finally:
            if timer:
                timer.cancel()
                timer.join()
        if expired.is_set():
            return error(408, 'UPLOAD_TIMEOUT', '接收 JSON 逾時。')
        if len(body) != size:
            return error(400, 'INCOMPLETE_BODY', '請求本文不完整。')
        if mode == 'share':
            from chatkeep import validate_url, ExtractionError
            from official_json import decode, OfficialError
            try:
                payload = decode(body)
            except OfficialError as exc:
                return error(exc.status, exc.code, str(exc))
            try:
                if not isinstance(payload, dict) or set(payload) != {'url'}: raise ValueError()
                validate_url(payload['url'])
            except (ValueError, TypeError, ExtractionError):
                return error(400, 'INVALID_URL', '請提供有效公開 ChatGPT 分享連結。')
        # No shell, private command arguments, tempfile or inherited stderr logging.
        process = subprocess.Popen([sys.executable, str(WORKER), mode], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            output, _ = process.communicate(body, timeout=CONVERSION_TIMEOUT)
        except subprocess.TimeoutExpired:
            return error(504, 'CONVERSION_TIMEOUT', '轉換逾時，已中止且未提供文件。')
        if process.returncode or len(output) > MAX_RESPONSE:
            return error(503, 'RESOURCE_LIMIT', '轉換超過資源限制或工作程序中止。')
        packet = json.loads(output)
        return respond(packet['status'], packet['value'])
    except Exception:
        return error(503, 'CONVERSION_FAILED', '無法安全完成轉換，請稍後重試。')
    finally:
        try:
            if process is not None:
                if process.poll() is None: process.kill()
                try:
                    process.communicate()  # Reap before releasing admission.
                finally:
                    for pipe in (process.stdin, process.stdout, process.stderr):
                        if pipe is not None: pipe.close()
        finally:
            slots.release()
