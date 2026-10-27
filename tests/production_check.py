"""Local gunicorn smoke test; optional live conversion, no deployment or artifacts."""
import argparse
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
ROOT=Path(__file__).resolve().parents[1]
LIVE='https://chatgpt.com/share/6acdedca-cfa0-83ec-9622-dba167dfee84'


def run(live=False):
    with socket.socket() as reserved:
        reserved.bind(('127.0.0.1',0));port=reserved.getsockname()[1]
    env=dict(os.environ,PORT=str(port))
    process=subprocess.Popen([sys.executable,'-m','gunicorn','--config','gunicorn.conf.py','server:application'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    base='http://127.0.0.1:%d'%port
    try:
        for attempt in range(50):
            try:
                with urllib.request.urlopen(base,timeout=1) as response:
                    assert response.status==200 and response.headers['Cache-Control']=='no-store'
                    break
            except (OSError,urllib.error.URLError):
                if process.poll() is not None:raise RuntimeError('Gunicorn exited before readiness')
                time.sleep(.2)
        else:raise RuntimeError('Gunicorn readiness timed out')
        def post(payload):
            return urllib.request.urlopen(urllib.request.Request(base+'/api/convert',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=100)
        try:post({'url':'https://invalid.test/SECRET_TEST_SENTINEL'})
        except urllib.error.HTTPError as error:assert error.code==400
        else:raise AssertionError('Unsafe URL accepted')
        evidence={'gunicorn_http':'passed','invalid_url':'rejected','access_logs':'disabled'}
        if live:
            with post({'url':LIVE}) as response:
                assert response.headers['Content-Type'].startswith('application/x-ndjson')
                assert response.headers['X-Accel-Buffering']=='no'
                events=[json.loads(line) for line in response if line.strip()]
            assert events[-1]['stage']=='done'
            doc=Document(BytesIO(base64.b64decode(events[-1]['document'])))
            count=sum(p.style.name=='Heading 2' for p in doc.paragraphs)
            assert count==events[-1]['report']['readable_messages']
            evidence['live_messages']=count
        print(json.dumps(evidence))
    finally:
        process.terminate()
        try:out,err=process.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill();out,err=process.communicate()
        assert b'SECRET_TEST_SENTINEL' not in out+err
        assert b'/share/' not in out+err

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    run(args.live)
