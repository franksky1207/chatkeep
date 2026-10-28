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
from zipfile import ZipFile
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
        # Exercise real multipart JSON IPC/HTTP, not just a mocked exporter.
        long = {'title':'PRIVATE_LONG_TITLE', 'current_node':'m99', 'mapping':{}}
        for i in range(100):
            key = 'm%d'%i
            long['mapping'][key] = {'parent':None if i==0 else 'm%d'%(i-1),
                'message':{'id':key,'author':{'role':'user' if i%2==0 else 'assistant'},
                'content':{'content_type':'text','parts':['PRIVATE_LONG_BODY_%03d\n'%i+'line\n'*1000]}}}
        long_request = urllib.request.Request(base+'/api/convert-json',data=json.dumps(long).encode(),
                                              headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(long_request,timeout=60) as response: large = json.load(response)
        assert large['artifact_type']=='zip' and large['mime_type']=='application/zip'
        assert large['report']['complete'] and large['report']['output_message_count']==100
        with ZipFile(BytesIO(base64.b64decode(large['document']))) as zipped:
            assert len(zipped.namelist())==large['report']['docx_volume_count']==2
            assert zipped.testzip() is None
            text=''.join(document_text(Document(BytesIO(zipped.read(n)))) for n in zipped.namelist())
            for i in range(100): assert text.count('PRIVATE_LONG_BODY_%03d'%i)==1
        try:
            urllib.request.urlopen(urllib.request.Request(base+'/api/convert-v2',data=b'{"url":"https://invalid.test"}',
                headers={'Content-Type':'application/json'}),timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code==400 and json.load(exc)['error']['code']=='INVALID_URL'
        else: raise AssertionError('v2 unsafe URL accepted')
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
        print('gunicorn JSON DOCX/ZIP, integrity, v2 URL rejection, upload deadline, slot reuse and privacy: passed')
    finally:
        process.terminate()
        try: out, err = process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill(); out, err = process.communicate()
        for private in (b'PRIVATE_BODY_SENTINEL', b'PRIVATE_TITLE_SENTINEL', b'OFF_BRANCH_SECRET', b'PRIVATE_LONG_BODY', b'PRIVATE_LONG_TITLE'):
            assert private not in out+err, 'private data leaked to logs'


if __name__ == '__main__': run()
