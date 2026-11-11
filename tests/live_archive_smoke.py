"""Public synthetic smoke against isolated Render test only. No user content."""
import base64
from io import BytesIO
import json
import plistlib
from urllib.request import Request, urlopen
from zipfile import ZipFile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_chatkeep import Encoder

BASE = 'https://chatkeep-v12-test.onrender.com'
SHARE = 'https://chatgpt.com/share/00000000-0000-0000-0000-000000000000'
conv = {'loaderData': {'route': {'serverResponse': {'data': {
    'title': '自動驗收', 'linear_conversation': [
        {'message': {'id': 'A', 'author': {'role': 'user'}, 'content': {'parts': ['早安']}}},
        {'message': {'id': 'B', 'author': {'role': 'assistant'}, 'content': {'parts': ['**午安**']}}}
    ]}}}}}
encoder=Encoder()
encoder.add(conv)
html='streamController.enqueue('+json.dumps(json.dumps(encoder.flat,ensure_ascii=False),ensure_ascii=False)+');'
archive=plistlib.dumps({'WebMainResource':{
    'WebResourceURL':SHARE,'WebResourceMIMEType':'text/html',
    'WebResourceData':html.encode()}},fmt=plistlib.FMT_BINARY)
body=json.dumps({'filename':'synthetic.webarchive',
                 'data':base64.b64encode(archive).decode()}).encode()

def post(route):
    req=Request(BASE+route,body,{'Content-Type':'application/json'},method='POST')
    with urlopen(req,timeout=45) as resp:
        assert resp.status==200,resp.status
        return json.load(resp)

reader=post('/api/archive-reader-v1')
assert reader['ok']
assert [m['text'] for m in reader['data']['messages']]==['早安','**午安**']
word=post('/api/archive-word-v1')
assert word['ok'] and word['artifact_type']=='docx'
with ZipFile(BytesIO(base64.b64decode(word['document']))) as z:
    assert z.testzip() is None
    assert 'word/document.xml' in z.namelist()
print('Live isolated Render archive HTML + DOCX smoke: PASS')
