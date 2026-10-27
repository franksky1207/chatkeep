"""Opt-in browser E2E. No live screenshots or conversation artifacts retained."""
import argparse
from contextlib import nullcontext
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sys
import threading
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docx import Document
from playwright.sync_api import sync_playwright, expect
from server import Handler, Server, RateLimit
from word_export import filename_for
from test_integration import html_for, URL
from docx_helpers import document_text

LIVE='https://chatgpt.com/share/6acdedca-cfa0-83ec-9622-dba167dfee84'


def synthetic_fetch(url,on_progress=None):
    body=html_for()
    if on_progress:
        for count in [0,len(body.encode())//2,len(body.encode())]:
            on_progress(count,len(body.encode()))
    return body


def download_document(page):
    with page.expect_download() as result:page.locator('#download').click()
    download=result.value
    if download.failure():raise AssertionError('Browser download failed')
    data=Path(download.path()).read_bytes()
    name=download.suggested_filename
    download.delete()
    return data,name


def run(live=False,browsers='chromium'):
    with Server(('127.0.0.1',0),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:%d'%server.server_port
            with (nullcontext() if live else patch('chatkeep.fetch_html',side_effect=synthetic_fetch)):
                with sync_playwright() as p:
                    for engine in (['chromium','webkit'] if browsers=='all' else [browsers]):
                        executable=(os.environ.get('CHATKEEP_CHROMIUM') or shutil.which('chromium')) if engine=='chromium' else p.webkit.executable_path
                        options={'executable_path':executable} if executable else {}
                        browser=getattr(p,engine).launch(**options,headless=True)
                        try:
                            for width,height in [(1280,900),(390,844),(320,740)]:
                                server.get_app().rates = RateLimit()  # Isolate browser cases; limits tested independently.
                                context=browser.new_context(viewport={'width':width,'height':height},accept_downloads=True)
                                page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                                page.goto(base)
                                expect(page.locator('#filename')).to_be_hidden()
                                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                                page.evaluate('''() => {
                                  window.qaEvents=[];
                                  const original=window.onEvent;
                                  window.onEvent = data => {
                                    original(data);
                                    qaEvents.push({stage:data.stage,current:data.current,total:data.total,percent:data.percent,
                                      meterHidden:document.getElementById('meter').hidden,
                                      meterValue:document.getElementById('meter').value,
                                      percentText:document.getElementById('percent').textContent,
                                      activityHidden:document.getElementById('activity').hidden,
                                      filenameVisible:!document.getElementById('result').hidden});
                                  };
                                }''')
                                page.locator('#url').fill(LIVE if live else URL)
                                page.locator('#start').click()
                                expect(page.locator('#download')).to_be_visible(timeout=100000)
                                expect(page.locator('#summary')).to_contain_text('尚未完成')
                                expect(page.locator('#filename')).to_be_visible()
                                expect(page.locator('#activity')).to_be_hidden()
                                expect(page.locator('#cancel')).to_be_hidden()
                                events=page.evaluate('qaEvents')
                                assert events and events[-1]['stage']=='done'
                                stage_order=['fetch','parse','word','pack','done'];last=-1
                                for event in events:
                                    stage=event['stage'];position=stage_order.index(stage)
                                    assert position>=last;last=position
                                    if stage!='done':assert not event['filenameVisible']
                                    if event.get('total'):
                                        expected=int(event['current']*100/event['total'])
                                        assert event['percent']==expected==event['meterValue']
                                        assert event['percentText']==str(expected)+'%'
                                    elif stage!='done':assert event['meterHidden']
                                pack=next(e for e in events if e['stage']=='pack')
                                assert pack['meterHidden']
                                data,default_name=download_document(page)
                                doc=Document(BytesIO(data))
                                count=sum(para.style.name=='Heading 2' for para in doc.paragraphs)
                                stats=page.locator('#stats dd').all_text_contents()
                                assert count==int(stats[2])
                                if not live:
                                    text=document_text(doc)
                                    assert '正文不能刪' in text and '繁體中文' in text
                                    original_hash=hashlib.sha256(data).digest()
                                    for name in ['中文測試','english report','../CON.txt','COM1','CON .txt','報告😀'*80,'name.docx','']:
                                        page.locator('#filename').fill(name)
                                        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                                        again,suggested=download_document(page)
                                        expected=filename_for(name.removesuffix('.docx')) if name else default_name
                                        assert suggested==expected
                                        assert suggested.endswith('.docx')
                                        assert hashlib.sha256(again).digest()==original_hash
                                    # Repeat conversion resets stale files/filename and succeeds again.
                                    page.locator('#start').click();expect(page.locator('#download')).to_be_visible(timeout=15000)
                                    expect(page.locator('#filename')).to_have_value('')
                                    _,again=download_document(page);assert again==default_name
                                    # Invalid URL removes the previous download.
                                    page.locator('#url').fill('https://evil.test/share/x');page.locator('#start').click()
                                    expect(page.locator('#error')).to_be_visible();expect(page.locator('#download')).to_be_hidden()
                                    # Controlled failures: truncated stream, backend failure, invalid payload.
                                    for body,expected in [('{"stage":"fetch","message":"test"}\n','不完整'),
                                      (json.dumps({'stage':'error','message':'擷取逾時，請稍後重試。'})+'\n','逾時'),
                                      ('invalid json\n',None)]:
                                        page.route('**/api/convert',lambda route,request,body=body:route.fulfill(status=200,content_type='application/x-ndjson',body=body))
                                        page.locator('#url').fill(URL);page.locator('#start').click()
                                        expect(page.locator('#error')).to_be_visible()
                                        if expected:expect(page.locator('#error')).to_contain_text(expected)
                                        expect(page.locator('#download')).to_be_hidden()
                                        page.unroute('**/api/convert')
                                    if width==1280:
                                        page.evaluate("""() => { window.realFetch=window.fetch; window.fetch=async()=>new Response(new ReadableStream({start(c){c.enqueue(new Uint8Array(26000001));c.close();}})); }""")
                                        page.locator('#start').click()
                                        expect(page.locator('#error')).to_contain_text('安全大小上限')
                                        expect(page.locator('#download')).to_be_hidden()
                                        page.evaluate('window.fetch=window.realFetch')
                                    # Cancellation and timeout of a genuinely pending connection.
                                    pending=[]
                                    page.route('**/api/convert',lambda route:pending.append(route))
                                    page.locator('#start').click();page.locator('#cancel').click()
                                    expect(page.locator('#error')).to_contain_text('取消')
                                    for route in pending:route.abort()
                                    page.unroute('**/api/convert');pending=[]
                                    page.clock.install()
                                    page.route('**/api/convert',lambda route:pending.append(route))
                                    page.locator('#start').click();page.clock.fast_forward(91000)
                                    expect(page.locator('#error')).to_contain_text('逾時')
                                    expect(page.locator('#download')).to_be_hidden()
                                    for route in pending:route.abort()
                                assert not errors
                                print(json.dumps({'mode':'live' if live else 'synthetic','engine':engine,'viewport':[width,height],
                                    'word_messages':count,'document_bytes':len(data),'progress_and_download':'passed',
                                    'filename_and_failure_flows':'not_repeated_live' if live else 'passed'}))
                                context.close()
                        finally:browser.close()
        finally:server.shutdown();thread.join()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--browser',choices=['chromium','webkit','all'],default='chromium');args=parser.parse_args()
    run(args.live,args.browser)
