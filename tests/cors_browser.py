"""Synthetic real-browser preflight using the shipped transport, no remote source.

WebKit here is Playwright Linux WebKit, not an iPhone Safari acceptance claim.
"""
import argparse
import base64
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import threading
from zipfile import ZipFile
from docx import Document
from playwright.sync_api import sync_playwright
from server import Application, Server, Handler

ROOT = Path(__file__).resolve().parents[1]


class Quiet(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT/'docs'), **kwargs)
    def log_message(self, *args):
        pass


def main(engine):
    pages = ThreadingHTTPServer(('127.0.0.1', 0), Quiet)
    origin = 'http://127.0.0.1:'+str(pages.server_port)
    os.environ['CHATKEEP_ALLOWED_ORIGINS'] = origin
    api = Server(('127.0.0.1', 0), Handler)
    base = 'http://localhost:'+str(api.server_port)
    app = Application()
    observed = []
    def capture(env, start):
        def response(status, headers):
            if env['REQUEST_METHOD'] == 'OPTIONS':
                observed.append((int(status.split()[0]),
                    set(x.strip().lower() for x in env.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS', '').split(',') if x.strip())))
            start(status, headers)
        return app(env, response)
    api.set_app(capture)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (pages, api)]
    for thread in threads:
        thread.start()
    try:
        with sync_playwright() as p:
            browser = (p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
                       if engine == 'chromium' else p.webkit.launch())
            try:
                page = browser.new_page()
                page.goto(origin)
                packet = page.evaluate('''async base=>{
                  const {transport}=await import('/local-backup/conversion.mjs');
                  const body={title:'Synthetic CORS',current_node:'a',mapping:{a:{parent:null,
                    message:{id:'a',author:{role:'user'},content:{content_type:'text',parts:['SYNTHETIC_CORS_TEXT']}}}}};
                  return await transport(base,'/api/convert-json',body);
                }''', base)
                assert packet['status'] == 200
                value = packet['value']
                assert value['report']['complete'] and value['report']['output_message_count'] == 1
                raw = base64.b64decode(value['document'], validate=True)
                with ZipFile(BytesIO(raw)) as archive:
                    assert archive.testzip() is None
                doc = Document(BytesIO(raw))
                assert 'SYNTHETIC_CORS_TEXT' in str(doc.element.xml)
                assert observed and all(status == 204 for status, _ in observed)
                assert all(headers <= {'content-type'} for _, headers in observed)
                print(engine+': shipped transport OPTIONS 204, POST 200, DOCX reopened and integrity verified')
            finally:
                browser.close()
    finally:
        for server in (pages, api):
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', choices=['chromium', 'webkit'], default='chromium')
    main(parser.parse_args().browser)
