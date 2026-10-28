"""Local Chromium simulation, synthetic data only; not Render/device acceptance.
Real cross-origin HTTP + workers + converter + downloads. Share fetching is injected.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import threading
from playwright.sync_api import sync_playwright, expect
from server import Application, Server, Handler
from official_worker import result

ROOT = Path(__file__).resolve().parents[1]


def conversation(title, text='PRIVATE_SELECTED', padding=0):
    return dict(title=title, id=title, current_node='a', metadata='PRIVATE_UNSENT_METADATA'+'x'*padding,
                mapping={'a': {'parent': None, 'message': {'id':'a', 'author':{'role':'user'},
                         'content':{'content_type':'text', 'parts':[text]}}}})


class Quiet(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT/'docs'), **kwargs)
    def log_message(self, *args): pass


def main():
    pages = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
    origin = 'http://127.0.0.1:'+str(pages.server_port)
    os.environ['CHATKEEP_ALLOWED_ORIGINS'] = origin+',https://franksky1207.github.io'
    api = Server(('127.0.0.1', 0), Handler)
    base = 'http://localhost:'+str(api.server_port)
    app = Application(); sent = []; preflights = []
    share_docx = result(json.dumps(conversation('Share DOCX')).encode(), 'official')
    many = conversation('Share ZIP'); many['mapping'] = {}
    for i in range(100):
        many['mapping'][str(i)] = {'parent': str(i-1) if i else None, 'message': {'id':str(i),
            'author':{'role':'user'}, 'content':{'content_type':'text','parts':['line\n'*1000]}}}
    many['current_node'] = '99'
    share_zip = result(json.dumps(many).encode(), 'official')
    share_docx['report']['source']='share_link'
    share_zip['report']['source']='share_link'
    shares = iter([share_docx, share_zip])

    def capture(env, start):
        if env['REQUEST_METHOD'] == 'OPTIONS': preflights.append(env['PATH_INFO'])
        if env['REQUEST_METHOD'] == 'POST':
            data = env['wsgi.input'].read(int(env['CONTENT_LENGTH']))
            sent.append((env['PATH_INFO'], data))
            if env['PATH_INFO'] == '/api/convert-v2':
                # Inject only remote public extraction; retain real API transport/CORS/converter.
                chosen = next(shares)
                from api_origin import cors_headers
                from server import HEADERS
                raw = json.dumps(chosen).encode()
                start('200 OK', HEADERS+cors_headers(env)+[('Content-Type','application/json'),('Content-Length',str(len(raw)))])
                return [raw]
            env['wsgi.input'] = BytesIO(data)
        return app(env, start)

    api.set_app(capture)
    for server in [pages, api]: threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as directory, sync_playwright() as p:
            browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
            page = browser.new_page(accept_downloads=True)
            errors=[];page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(origin)
            page.locator('#service-settings').evaluate('(el)=>el.open=true')
            page.locator('#api-base').fill(base)
            page.locator('#tab-backup').click()
            page.locator('#raw-download').evaluate('(el)=>el.open=true')
            data = [conversation('Selected one'), conversation('PRIVATE_OTHER', 'NEVER_SEND'),
                    conversation('Selected large', padding=2_100_000)]
            path=Path(directory)/'conversations.json';path.write_text(json.dumps(data))
            page.locator('#files').set_input_files(path)
            page.locator('#scan').click()
            expect(page.locator('#progress')).to_contain_text('索引完成', timeout=20000)
            page.locator('#search').fill('Selected')
            page.locator('#select-visible').click()
            expect(page.locator('#count')).to_contain_text('已選 2 段')
            page.locator('#results button').first.click()
            expect(page.locator('#preview')).to_contain_text('僅索引資料')
            # Independent raw JSON download preserves the entire selected object.
            page.locator('#deselect').click();page.locator('#results input').first.check()
            with page.expect_download() as info: page.locator('#download').click()
            downloaded=info.value;downloaded.save_as(Path(directory)/'raw.json')
            assert json.loads((Path(directory)/'raw.json').read_bytes())==data[0]
            page.locator('#select-visible').click()
            page.locator('#convert-selected').click()
            expect(page.locator('#conversion-results')).to_contain_text('browser_derived_sequence', timeout=30000)
            expect(page.locator('#conversion-results button', has_text='下載 DOCX')).to_have_count(2)
            assert len(sent)==2 and [x[0] for x in sent]==['/api/convert-json','/api/convert-chunk-v1']
            assert all(b'NEVER_SEND' not in raw and b'PRIVATE_OTHER' not in raw for _,raw in sent)
            assert b'PRIVATE_UNSENT_METADATA' not in sent[1][1]
            for button in page.locator('#conversion-results button', has_text='下載 DOCX').all():
                with page.expect_download() as info: button.click()
                assert info.value.suggested_filename.endswith('.docx')
                info.value.save_as(Path(directory)/'out.docx')
                assert (Path(directory)/'out.docx').read_bytes()[:2]==b'PK'
            # New job disposes old results, both share artifact types download locally.
            page.locator('#clear-conversion').click()
            page.locator('#tab-share').click()
            for kind in ['DOCX','ZIP']:
                page.locator('#share-url').fill('https://chatgpt.com/share/00000000-0000-0000-0000-000000000000')
                page.locator('#convert-share').click()
                b=page.locator('#conversion-results button', has_text='下載 '+kind)
                expect(b).to_be_visible(timeout=20000)
                with page.expect_download() as info: b.click()
                assert info.value.suggested_filename.lower().endswith('.'+kind.lower())
                page.locator('#clear-conversion').click()
            # Actual rejected cross-origin API fetch, rather than a mocked browser error.
            rejected=page.evaluate('''async base=>{try{const r=await fetch(base+'/api/convert-json',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'forbidden'},body:'{}'});return r.status;}catch{return 'blocked';}}''',base)
            assert rejected=='blocked'
            # Injected network failure is distinct from browser cancellation.
            page.route('**/api/convert-v2', lambda route: route.abort('failed'))
            page.locator('#convert-share').click()
            expect(page.locator('#conversion-results')).to_contain_text('NETWORK_OR_CORS', timeout=20000)
            page.locator('#cancel-conversion').click()
            expect(page.locator('#conversion-results button:visible',has_text='下載')).to_have_count(0)
            page.unroute('**/api/convert-v2')
            page.locator('#clear-conversion').click()
            held=[]
            page.route('**/api/convert-v2', lambda route: held.append(route))
            page.locator('#convert-share').click()
            page.wait_for_timeout(6600)
            assert held, 'active fetch must have started before cancellation'
            page.locator('#cancel-conversion').click()
            expect(page.locator('#conversion-results')).to_contain_text('已取消')
            expect(page.locator('#clear-conversion')).to_be_enabled(timeout=5000)
            try: held[0].fulfill(status=200, content_type='application/json', body=json.dumps(share_docx))
            except Exception: pass  # Native fetch abort may already dispose the route.
            expect(page.locator('#conversion-results button:visible',has_text='下載')).to_have_count(0)
            page.unroute('**/api/convert-v2')
            page.locator('#clear-conversion').click()
            expect(page.locator('#conversion-results')).to_be_empty()
            assert '/api/convert-json' in preflights and '/api/convert-chunk-v1' in preflights
            assert not errors, errors
            browser.close()
        print('PASS: local Chromium dual entry, workers, real cross-site CORS, selected-only uploads, metadata exclusion, raw JSON, DOCX/ZIP downloads, network failure/cancel cleanup; public extraction injected.')
    finally:
        for server in [pages,api]:server.shutdown();server.server_close()


if __name__=='__main__':main()
