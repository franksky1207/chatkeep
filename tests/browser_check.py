"""Opt-in Chromium E2E; synthetic by default, --live uses the supplied public URL.

No screenshots or conversation artifacts are kept. Browser downloads are read in
Playwright's temporary directory and deleted before returning.
"""
import argparse
from contextlib import nullcontext
from io import BytesIO
import json
import os
import shutil
from pathlib import Path
import sys
import threading
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docx import Document
from playwright.sync_api import sync_playwright, expect
from server import Handler, Server
from test_integration import html_for, TEXT, URL

LIVE = 'https://chatgpt.com/share/6acdedca-cfa0-83ec-9622-dba167dfee84'


def run(live=False):
    with Server(('127.0.0.1',0),Handler) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base='http://127.0.0.1:%d'%server.server_port
            with (nullcontext() if live else patch('chatkeep.fetch_html',return_value=html_for())):
                with sync_playwright() as p:
                    executable=os.environ.get('CHATKEEP_CHROMIUM') or shutil.which('chromium')
                    options={'executable_path':executable} if executable else {}
                    browser=p.chromium.launch(**options,headless=True,args=['--no-sandbox'])
                    try:
                        for width,height in [(1280,900),(390,844)]:
                            context=browser.new_context(viewport={'width':width,'height':height},accept_downloads=True)
                            page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                            page.goto(base)
                            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                            page.get_by_label('ChatGPT 公開分享連結',exact=True).fill(LIVE if live else URL)
                            page.get_by_role('button',name='開始轉換').click()
                            expect(page.locator('#download')).to_be_visible(timeout=90000)
                            assert '尚未完成逐訊息比對' in page.locator('#summary').inner_text()
                            with page.expect_download() as info:page.get_by_role('link',name='下載 Word').click()
                            download=info.value
                            if download.failure():raise AssertionError('browser download failed')
                            data=Path(download.path()).read_bytes();download.delete()
                            document=Document(BytesIO(data))
                            bodies=[para for para in document.paragraphs if para.style.name=='Heading 2']
                            if live:
                                # HTTP report and Word count independently agree.
                                stats=page.locator('#stats dd').all_text_contents()
                                assert len(bodies)==int(stats[2])
                            else:
                                combined='\n'.join(p.text for p in document.paragraphs)+'\n'+'\n'.join(c.text for t in document.tables for row in t.rows for c in row.cells)
                                assert '正文不能刪' in combined and '繁體中文' in combined
                            assert not errors
                            print(json.dumps({'mode':'live' if live else 'synthetic','viewport':[width,height],'download_bytes':len(data),'word_messages':len(bodies),'result':'passed'}))
                            if not live:
                                # Invalid URL: old download must disappear immediately.
                                page.get_by_label('ChatGPT 公開分享連結',exact=True).fill('https://evil.test/share/x')
                                page.get_by_role('button',name='開始轉換').click()
                                expect(page.locator('#error')).to_be_visible()
                                expect(page.locator('#download')).to_be_hidden()
                                # A truncated NDJSON response must never show success.
                                page.route('**/api/convert',lambda route:route.fulfill(status=200,content_type='application/x-ndjson',body='{"stage":"fetch","message":"test"}\n'))
                                page.locator('#url').fill(URL);page.locator('#start').click()
                                expect(page.locator('#error')).to_contain_text('不完整')
                                expect(page.locator('#download')).to_be_hidden()
                                page.unroute('**/api/convert')
                                # Server timeout is rendered, not mistaken for a download.
                                page.route('**/api/convert',lambda route:route.fulfill(status=200,content_type='application/x-ndjson',body=json.dumps({'stage':'error','message':'擷取逾時，請稍後重試。'})+'\n'))
                                page.locator('#start').click();expect(page.locator('#error')).to_contain_text('逾時')
                                page.unroute('**/api/convert')
                                # Client deadline on a stalled connection (virtual clock).
                                page.clock.install()
                                pending=[]
                                page.route('**/api/convert',lambda route:pending.append(route))
                                page.locator('#start').click();page.clock.fast_forward(91000)
                                expect(page.locator('#error')).to_contain_text('逾時')
                                expect(page.locator('#download')).to_be_hidden()
                                for route in pending: route.abort()
                                print(json.dumps({'viewport':width,'error_flows':'invalid URL / interrupted stream / upstream timeout / client timeout passed'}))
                            context.close()
                    finally:browser.close()
        finally:
            server.shutdown();thread.join()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');args=parser.parse_args()
    run(args.live)
