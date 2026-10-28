"""Batch 4 local gunicorn HTTP/privacy smoke test; no deployment or live source."""
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from docx import Document
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_official_json import conversation
from docx_helpers import document_text

ROOT = Path(__file__).resolve().parents[1]


def run():
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1', 0)); port = reserved.getsockname()[1]
    process = subprocess.Popen([sys.executable, '-m', 'gunicorn', '--config', 'gunicorn.conf.py',
                                'server:application'], cwd=ROOT, env=dict(os.environ, PORT=str(port)),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    base = 'http://127.0.0.1:%d' % port
    try:
        for _ in range(50):
            try:
                with urllib.request.urlopen(base, timeout=1) as response:
                    assert response.status == 200
                break
            except OSError: time.sleep(.1)
        else: raise AssertionError('gunicorn readiness timeout')
        c = conversation(); c['title'] = 'PRIVATE_TITLE_SENTINEL'
        c['mapping']['a']['message']['content']['parts'] = ['PRIVATE_BODY_SENTINEL']
        request = urllib.request.Request(base+'/api/convert-json', data=json.dumps(c).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=60) as response:
            packet = json.load(response)
            assert response.headers['Cache-Control'] == 'no-store'
        doc = Document(BytesIO(base64.b64decode(packet['document'])))
        assert 'PRIVATE_BODY_SENTINEL' in document_text(doc)
        assert 'OFF_BRANCH_SECRET' not in document_text(doc)
        try:
            urllib.request.urlopen(urllib.request.Request(base+'/api/convert-json', data=b'{',
                headers={'Content-Type': 'application/json'}), timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code == 400 and json.load(exc)['error']['code'] == 'INVALID_JSON'
        else: raise AssertionError('invalid JSON accepted')
        # Actually stall an upload: gunicorn.socket watchdog must unblock the read.
        with socket.create_connection(('127.0.0.1', port), timeout=15) as slow:
            slow.sendall(('POST /api/convert-json HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nContent-Type: application/json\r\nContent-Length: 1000\r\nConnection: close\r\n\r\n{' % port).encode())
            reply = b''
            while True:
                chunk = slow.recv(65536)
                if not chunk: break
                reply += chunk
            assert b'408' in reply and b'UPLOAD_TIMEOUT' in reply
        # The shared admission slot is free after upload cancellation.
        with urllib.request.urlopen(request, timeout=60) as response: assert json.load(response)['ok']
        print('gunicorn JSON success/error, DOCX, upload deadline, slot reuse and privacy: passed')
    finally:
        process.terminate()
        try: out, err = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill(); out, err = process.communicate()
        for private in (b'PRIVATE_BODY_SENTINEL', b'PRIVATE_TITLE_SENTINEL', b'OFF_BRANCH_SECRET'):
            assert private not in out+err, 'private data leaked to logs'


if __name__ == '__main__': run()
