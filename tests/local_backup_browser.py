"""Batch 2 only: real-browser local JSON/ZIP tests; generated fixtures never committed.
Run: .venv/bin/python tests/local_backup_browser.py [--stress] [--browser chromium|webkit]
"""
import argparse
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import random
import shutil
import struct
import tempfile
import threading
import time
import zipfile
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


class Quiet(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs): super().__init__(*args, directory=str(ROOT/'docs'), **kwargs)
    def log_message(self, *args): pass


def conversation(i, title=None):
    return {'title': title or f'繁體中文 English 😀 對話 {i:04d}', 'id': str(i), 'create_time': 1, 'update_time': 2,
            'mapping': {'root': {'message': None, 'parent': None, 'children': ['a', 'b']},
                        'a': {'parent': 'root', 'children': [], 'message': {'author': {'role': 'assistant'}, 'content': {'content_type': 'text', 'parts': ['括號 {[]} 跳脫 " \\ \n 中文😀']}}},
                        'b': {'parent': 'root', 'children': [], 'message': {'author': {'role': 'tool'}, 'metadata': {'is_visually_hidden_from_conversation': True}, 'content': {'content_type': 'unknown', 'future': [1, None, True]}}}},
            'current_node': 'a', 'unknown': {'原樣保留': [False, {}]}}


def encode(obj): return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).encode()


def generate_stress(path, mib=440, single=False):
    """Exact size, many unique conversations or one very large mapping; no full-file buffer."""
    target = mib * 1048576
    rng = random.Random(101)
    records = []
    with path.open('wb') as out:
        out.write(b'[{"title":"large mapping","id":"single","mapping":{ ' if single else b'[')
        i = 0
        # Per-record incompressible seed + repeated runs gives a realistic, safe ZIP ratio.
        while out.tell() < target - 180000:
            if i: out.write(b',')
            start = out.tell()
            seed = ''.join(rng.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16384))
            if single:
                raw = encode({'message': {'author': {'role': 'tool'}, 'content': {'content_type': 'unknown', 'parts': [seed * 8]}}, 'parent': None, 'children': []})
                out.write(encode(str(i)) + b':' + raw)
            else:
                c = conversation(i); c['mapping']['a']['message']['content']['parts'].append(seed * 8)
                raw = encode(c); out.write(raw)
                records.append((i, start, out.tell(), hashlib.sha256(raw).hexdigest()))
            i += 1
        if single:
            out.write(b'},"padding":"')
            out.write(b' ' * (target - out.tell() - 3)); out.write(b'"}]')
        else:
            out.write(b',{"title":"stress tail","id":"tail","mapping":{},"padding":"')
            out.write(b' ' * (target - out.tell() - 3)); out.write(b'"}]')
    assert path.stat().st_size == target
    return i if single else records


class MemorySampler:
    """Linux RSS includes shared pages more than once: evidence, not exact private heap."""
    def __init__(self): self.stop = threading.Event(); self.peak = 0; self.baseline = 0; self.anon_peak = 0; self.file_peak = 0
    @staticmethod
    def sample():
        processes = {}
        for folder in Path('/proc').iterdir():
            if not folder.name.isdigit(): continue
            try:
                stat = (folder/'stat').read_text(); tail = stat[stat.rfind(')')+2:].split()
                status = dict(line.split(':', 1) for line in (folder/'status').read_text().splitlines() if ':' in line)
                processes[int(folder.name)] = (int(tail[1]), int(tail[21]) * os.sysconf('SC_PAGE_SIZE'), int(status.get('RssAnon','0 kB').split()[0])*1024, int(status.get('RssFile','0 kB').split()[0])*1024)
            except (OSError, ValueError, IndexError): pass
        descendants = {os.getpid()}
        while True:
            more = {pid for pid, info in processes.items() if info[0] in descendants}
            if more <= descendants: break
            descendants |= more
        return tuple(sum(info[i] for pid, info in processes.items() if pid in descendants and pid != os.getpid()) for i in [1,2,3])
    def __enter__(self):
        self.baseline, self.anon_baseline, self.file_baseline = self.sample(); self.peak = self.baseline; self.anon_peak = self.anon_baseline; self.file_peak = self.file_baseline
        def run():
            while not self.stop.wait(.1):
                rss, anon, file = self.sample(); self.peak = max(self.peak, rss); self.anon_peak = max(self.anon_peak, anon); self.file_peak = max(self.file_peak, file)
        self.thread = threading.Thread(target=run, daemon=True); self.thread.start(); return self
    def __exit__(self, *args): self.stop.set(); self.thread.join()


def run(stress=False, engine='chromium'):
    with tempfile.TemporaryDirectory(prefix='chatkeep-batch2-') as temporary:
        tmp = Path(temporary)
        objects = [conversation(i, '重複 title 😀' if i < 2 else None) for i in range(365)]
        # Also preserve deep unknown fields without mapping interpretation.
        nested = {'leaf': '底部'}
        for _ in range(100): nested = {'nested': [nested]}
        objects[0]['mapping']['b']['deep'] = nested
        a, b = tmp/'conversations-000.json', tmp/'conversations-001.json'
        a.write_bytes(b'[\n'+b',\n'.join(encode(c) for c in objects[:180])+b'\n]')
        b.write_bytes(encode(objects[180:]))
        bad = tmp/'broken.json'; bad.write_bytes(b'[{"mapping":{}}] trailing')
        empty = tmp/'empty.json'; empty.write_bytes(b'')
        archive = tmp/'official.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(a, 'export/conversations-000.json'); z.write(b, 'conversations-001.json')
            z.writestr('media/unrelated.bin', b'ignored'); z.writestr('other.json', b'not conversations')
        mixed = tmp/'mixed.zip'
        with zipfile.ZipFile(mixed,'w',zipfile.ZIP_DEFLATED) as z:
            z.write(a,'conversations-000.json');z.writestr('conversations-001.json',bad.read_bytes());z.write(b,'conversations-002.json')
        corrupt = tmp/'corrupt.zip'; corrupt.write_bytes(b'broken zip')
        crc_bad = tmp/'crc.zip'
        with zipfile.ZipFile(crc_bad,'w',zipfile.ZIP_STORED) as z: z.writestr('conversations.json',encode([objects[0]]))
        raw = bytearray(crc_bad.read_bytes()); raw[30+len('conversations.json')+1] ^= 1; crc_bad.write_bytes(raw)
        bomb = tmp/'ratio.zip'
        with zipfile.ZipFile(bomb,'w',zipfile.ZIP_DEFLATED) as z: z.writestr('conversations.json',b' '*2000000)
        server=ThreadingHTTPServer(('127.0.0.1',0),Quiet);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as p:
                context=getattr(p,engine).launch_persistent_context(str(tmp/'browser-profile'),headless=True,accept_downloads=True,**({'executable_path':shutil.which('chromium')} if engine=='chromium' else {}))
                browser=context.browser
                external=[]; errors=[]
                context.on('request',lambda r:external.append(r.url) if not r.url.startswith(('http://127.0.0.1:','blob:')) else None)
                page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                expect(page.locator('#scan')).to_be_enabled();expect(page.locator('#cancel')).to_be_hidden()
                page.wait_for_timeout(100)
                def scan(paths, count=None):
                    page.locator('#files').set_input_files([str(x) for x in paths]); page.locator('#scan').click()
                    expect(page.locator('#progress')).to_contain_text('索引完成',timeout=180000)
                    if count is not None: expect(page.locator('#progress')).to_contain_text(f'{count} 段對話')
                    expect(page.locator('#cancel')).to_be_hidden()
                def download_one(query, expected=None, expected_hash=None):
                    page.locator('#deselect').click();page.locator('#search').fill(query)
                    expect(page.locator('#results input')).to_have_count(1)
                    page.locator('#results input').check()
                    with page.expect_download(timeout=30000) as event: page.locator('#download').click()
                    download=event.value; path=tmp/'download.json';download.save_as(path);download.delete()
                    expect(page.locator('#export-status')).to_contain_text('已啟動',timeout=30000)
                    if expected is not None:
                        assert path.read_bytes()==encode(expected)
                        assert json.loads(path.read_bytes())==expected
                    if expected_hash:
                        digest=hashlib.sha256()
                        with path.open('rb') as f:
                            while chunk:=f.read(1048576):digest.update(chunk)
                        assert digest.hexdigest()==expected_hash
                scan([a],180)
                scan([a,b],365)
                expect(page.locator('#results input')).to_have_count(300)
                page.locator('#select-visible').click();expect(page.locator('#count')).to_have_text('已選 365 段')
                page.locator('#deselect').click();expect(page.locator('#count')).to_have_text('已選 0 段')
                download_one('對話 0350',objects[350])
                page.locator('#search').fill('重複 title');expect(page.locator('#results input')).to_have_count(2)
                page.locator('#deselect').click();page.locator('#results input').nth(0).check()
                with page.expect_download() as d:page.locator('#download').click()
                d.value.save_as(tmp/'duplicate.json');d.value.delete()
                assert (tmp/'duplicate.json').read_bytes()==encode(objects[0])
                expect(page.locator('#export-status')).to_contain_text('已啟動')
                page.locator('#deselect').click();page.locator('#select-visible').click()
                expect(page.locator('#count')).to_have_text('已選 2 段')
                downloads=[];listener=lambda item:downloads.append(item);page.on('download',listener)
                page.locator('#download').click();expect(page.locator('#export-status')).to_contain_text('已啟動 2 個',timeout=30000)
                page.wait_for_timeout(100);page.remove_listener('download',listener)
                assert len(downloads)==2
                actual=[]
                for i,item in enumerate(downloads):
                    path=tmp/f'multi-{i}.json';item.save_as(path);item.delete();actual.append(path.read_bytes())
                assert actual==[encode(objects[0]),encode(objects[1])]
                scan([a,bad,empty,b],365)
                expect(page.locator('#progress')).to_contain_text('broken.json')
                expect(page.locator('#progress')).to_contain_text('empty.json')
                download_one('對話 0350',objects[350])
                page.locator('#search').fill('')
                scan([mixed],365)
                expect(page.locator('#progress')).to_contain_text('conversations-001.json')
                download_one('對話 0350',objects[350])
                page.locator('#search').fill('')
                scan([archive],365)
                assert '失敗' not in page.locator('#progress').inner_text(),page.locator('#progress').inner_text()
                download_one('對話 0350',objects[350])
                assert page.evaluate('''async()=>{const r=await navigator.storage.getDirectory();let n=0;for await(const [name]of r.entries())if(name.startsWith('chatkeep-backup-'))n++;return n}''')==1
                page.locator('#reset').click();expect(page.locator('#progress')).to_contain_text('已清除')
                assert page.evaluate('''async()=>{const r=await navigator.storage.getDirectory();let n=0;for await(const [name]of r.entries())if(name.startsWith('chatkeep-backup-'))n++;return n}''')==0
                for invalid, reason in [(corrupt,'ZIP'),(crc_bad,'CRC32'),(bomb,'壓縮比例')]:
                    scan([invalid],0);expect(page.locator('#progress')).to_contain_text(reason)
                    expect(page.locator('#picker')).to_be_hidden()
                scan([a],180)
                for width in [1280,390,320]:
                    page.set_viewport_size({'width':width,'height':900})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    assert page.locator('a[href="https://chatkeep.onrender.com/"]').count()==2
                denied=context.new_page()
                denied.add_init_script("Object.defineProperty(navigator.storage,'getDirectory',{value:async()=>{throw new DOMException('denied','SecurityError')}})")
                denied.goto(f'http://127.0.0.1:{server.server_port}/')
                denied.locator('#files').set_input_files([str(a),str(archive)]);denied.locator('#scan').click()
                expect(denied.locator('#progress')).to_contain_text('索引完成',timeout=30000)
                expect(denied.locator('#progress')).to_contain_text('180 段對話')
                expect(denied.locator('#progress')).to_contain_text('本機暫存空間')
                denied.locator('#reset').click();expect(denied.locator('#progress')).to_contain_text('已清除')
                denied.close()
                print(json.dumps({'browser':engine,'version':browser.version,'profile':'persistent (normal browsing; OPFS on disk)','functional':'passed','cases':'single/multiple JSON; ZIP deflate; Unicode/deep/branches/unknown fields; exact bytes/structure; 365 search results; duplicate titles; partial failure; empty/corrupt JSON and ZIP; CRC/ratio; ZIP partial failure; OPFS reset cleanup; storage denied fallback; desktop/mobile layout; Render links preserved'},ensure_ascii=False),flush=True)
                if stress:
                    page.set_viewport_size({'width':1280,'height':900})
                    large=tmp/'440MiB.json';started=time.monotonic();records=generate_stress(large)
                    print(json.dumps({'fixture_bytes':large.stat().st_size,'conversations':len(records)+1,'generation_seconds':round(time.monotonic()-started,2)}),flush=True)
                    # Cancellation after scanning has started, and double-click cannot start two workers.
                    page.locator('#files').set_input_files(str(large));page.locator('#scan').click()
                    expect(page.locator('#progress')).to_contain_text('建立索引',timeout=30000)
                    assert page.locator('#scan').is_disabled() and page.locator('#files').is_disabled()
                    started=time.monotonic();page.locator('#cancel').click();expect(page.locator('#progress')).to_contain_text('已取消',timeout=10000)
                    assert page.locator('#picker').is_hidden()
                    print(json.dumps({'cancel_seconds':round(time.monotonic()-started,3),'stale_results':'cleared'}),flush=True)
                    def stress_scan(paths,label,count):
                        page.evaluate('''()=>{window.ticks=[];window.lastTick=performance.now();window.heartbeat=setInterval(()=>{let now=performance.now();window.ticks.push(now-window.lastTick);window.lastTick=now},50)}''')
                        started=time.monotonic()
                        with MemorySampler() as memory:scan(paths,count)
                        timing=page.evaluate('''()=>{clearInterval(window.heartbeat);return {ticks:ticks.length,max_gap_ms:Math.max(...ticks)}}''')
                        result={'target':label,'seconds':round(time.monotonic()-started,2),'rss_baseline_mib':round(memory.baseline/1048576,1),'rss_peak_mib':round(memory.peak/1048576,1),'anon_baseline_mib':round(memory.anon_baseline/1048576,1),'anon_peak_mib':round(memory.anon_peak/1048576,1),'file_baseline_mib':round(memory.file_baseline/1048576,1),'file_peak_mib':round(memory.file_peak/1048576,1),'rss_measurement':'sum of Python-child process RSS, shared pages counted repeatedly',**timing}
                        print(json.dumps(result),flush=True)
                        assert timing['ticks']>5 and timing['max_gap_ms']<3000,result
                    stress_scan([large],'440 MiB JSON',len(records)+1)
                    for record in [records[0],records[len(records)//2],records[-1]]:
                        i,start,end,digest=record;download_one(f'對話 {i:04d}',expected_hash=digest)
                    print(json.dumps({'stress_extract_first_middle_last':'exact SHA256 passed'}),flush=True)
                    zipped=tmp/'440MiB.zip'
                    with zipfile.ZipFile(zipped,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:z.write(large,'export/conversations-000.json')
                    # Cancel while ZIP is actually being decompressed; all OPFS temporary entries must go.
                    page.locator('#files').set_input_files(str(zipped));page.locator('#scan').click()
                    expect(page.locator('#progress')).to_contain_text('本機解壓',timeout=30000)
                    page.locator('#cancel').click();expect(page.locator('#progress')).to_contain_text('已取消',timeout=10000)
                    assert page.evaluate('''async()=>{const r=await navigator.storage.getDirectory();let n=0;for await(const [name]of r.entries())if(name.startsWith('chatkeep-backup-'))n++;return n}''')==0
                    stress_scan([zipped],'440 MiB decompressed ZIP',len(records)+1)
                    download_one(f'對話 {records[len(records)//2][0]:04d}',expected_hash=records[len(records)//2][3])
                    page.locator('#reset').click();expect(page.locator('#progress')).to_contain_text('已清除')
                    single=tmp/'single-440MiB.json';nodes=generate_stress(single,single=True)
                    stress_scan([single],'single 440 MiB conversation mapping',1)
                    # Stream-download hash against the original object range; no test JSON.parse of 440 MiB.
                    digest=hashlib.sha256()
                    with single.open('rb') as f:
                        f.seek(1);remaining=single.stat().st_size-2
                        while remaining:
                            data=f.read(min(1048576,remaining));digest.update(data);remaining-=len(data)
                    download_one('large mapping',expected_hash=digest.hexdigest())
                    print(json.dumps({'single_mapping_nodes':nodes,'single_440MiB_extract':'exact SHA256 passed','compressed_zip_bytes':zipped.stat().st_size,'zip_cancel_cleanup':'passed'}),flush=True)
                assert not errors,errors
                assert not external,external
                print(json.dumps({'uncaught_page_errors':errors,'external_network_requests':external}),flush=True)
                page.locator('#reset').click();expect(page.locator('#progress')).to_contain_text('已清除')
                context.close();browser.close()
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stress',action='store_true');parser.add_argument('--browser',choices=['chromium','webkit'],default='chromium');args=parser.parse_args()
    run(args.stress,args.browser)
