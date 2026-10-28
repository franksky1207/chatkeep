"""Batch 7 synthetic UI/a11y/viewports; local Chromium, not device acceptance.
Queue-state tests inject a presentation-only fake. Real transport/Worker/download
verification is covered separately by pages_integration_browser.py.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
TITLE = '<img src=x onerror="window.PRIVATE_XSS=1">'+'長對話名稱'*50
REPORT = dict(source='official_json', integrity_basis='normalized_output_sequence', output_message_count=2,
              docx_volume_count=1, missing=False, status='converted_with_warnings', raw_node_count=5,
              active_path_message_count=4, off_branch_node_count=1, skipped_categories={'tool':1,'hidden':1},
              warnings=[{'code':'SYNTHETIC','message':'<script>window.PRIVATE_XSS=2</script>'}],
              sequence_sha256='a'*64, volumes=[dict(number=1,first_message=1,last_message=2,file_sha256='b'*64)])
# Only injected into a routed test entry module, never shipped or exposed by the app.
FAKE_APP = '''
import {mountConversion} from './conversion-ui.mjs';
import {mountModes} from './site-ui.mjs';
mountModes();
const report=REPORT;
class FakeQueue {
 constructor(options){Object.assign(this,{options,jobs:[],running:false,retained:0,controller:new AbortController()});window.testQueue=this;}
 emit(job){this.current=job;this.options.onUpdate(job,this);}
 async run(items){this.jobs=items.map((item,i)=>({item,title:item.title,state:'pending',stage:'等待',type:'docx'}));
  this.jobs[0].state='done';this.jobs[0].stage='下載準備完成';this.jobs[0].report=structuredClone(report);this.jobs[0].artifact={artifact_type:'docx',mime_type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename:'CON.docx',blob:new Blob(['PK synthetic UI-only download'])};
  this.jobs[1].state='failed';this.jobs[1].stage='失敗';this.jobs[1].error='NETWORK_OR_CORS';this.jobs[1].collector={results:new Map([[1,{}]])};this.jobs[1].failedPart=2;
  this.jobs[2].state='released';this.jobs[3].state='skipped';this.jobs[4].state='cancelled';this.retained=this.jobs[0].artifact.blob.size;this.emit(this.jobs[1]);}
 async resume(){const job=this.jobs.find(j=>j.state==='failed');if(job){job.state='working';job.stage='上傳批次 2 / 4；Render 正在轉換';this.running=true;this.emit(job);} }
 skip(job){job.state='skipped';this.emit(job);}
 release(job){this.retained-=job.artifact.blob.size;job.artifact=null;job.state='released';this.emit(job);}
 cancel(){this.controller.abort();this.running=false;for(const job of this.jobs)if(['pending','working','failed'].includes(job.state)){job.state='cancelled';job.collector=null;this.emit(job);}}
 dispose(){this.cancel();this.jobs=[];this.retained=0;}
}
mountConversion({getSelected:()=>Array.from({length:125},(_,i)=>({title:i?'等待 '+i:TITLE})),extract:()=>{},setLocked:()=>{},queueFactory:options=>new FakeQueue(options)});
'''.replace('REPORT',json.dumps(REPORT)).replace('TITLE',json.dumps(TITLE))


class Quiet(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT/'docs'),**kw)
    def log_message(self,*a):pass


def fixture(i):
    return dict(title=('系列1' if i<2 else '系列'+str(i+1))+' '+('長名稱'*40 if i==0 else '合成對話'),
                id=str(i),create_time=1704067200,update_time=1704153600,current_node='a',mapping={
                'a':{'parent':None,'message':{'id':'a','author':{'role':'user'},'content':{'content_type':'text','parts':['PRIVATE_BODY_'+str(i)]}}}})


class UISecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Quiet)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.origin='http://127.0.0.1:'+str(cls.server.server_port)
        cls.playwright=sync_playwright().start();cls.browser=cls.playwright.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.playwright.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def open(self,fake=False,init=None):
        self.context=self.browser.new_context(accept_downloads=True)
        self.page=self.context.new_page();self.errors=[];self.external=[]
        if init:self.page.add_init_script(init)
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        self.page.on('request',lambda request:self.external.append(request.url) if not request.url.startswith(self.origin) and not request.url.startswith('blob:') else None)
        if fake:self.page.route('**/local-backup/app.mjs',lambda route:route.fulfill(status=200,content_type='text/javascript',body=FAKE_APP))
        self.page.goto(self.origin)
        return self.page
    def tearDown(self):
        self.assertFalse(self.errors);self.assertFalse(self.external);self.context.close()
    def scan(self,page,n=365):
        data=[fixture(i) for i in range(n)]
        page.locator('#tab-backup').click()
        page.locator('#files').set_input_files({'name':'conversations.json','mimeType':'application/json','buffer':json.dumps(data).encode()})
        page.locator('#scan').click();expect(page.locator('#progress')).to_contain_text('索引完成',timeout=20000)
        return data
    def start_fake(self,page):
        page.locator('#service-settings').evaluate('(el)=>el.open=true');page.locator('#api-base').fill('http://localhost:8000')
        page.locator('#convert-selected').evaluate('(el)=>{el.disabled=false;el.click()}')
        expect(page.locator('#queue-summary')).to_contain_text('共 125 段')
    def assert_layout(self,page):
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        offenders=page.evaluate('''()=>[...document.querySelectorAll('button:not([hidden]),input:not([type=checkbox]),select,summary')].filter(e=>{
 const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width&&r.height&&s.visibility!=='hidden'&&(r.left<0||r.right>innerWidth+1||r.height<43);
 }).map(e=>e.id||e.textContent.slice(0,50))''')
        self.assertFalse(offenders,offenders)
    def test_modes_keyboard_service_validation_and_privacy(self):
        page=self.open();expect(page.locator('#mode-share')).to_be_visible();expect(page.locator('#mode-backup')).to_be_hidden()
        page.locator('#tab-share').focus();page.keyboard.press('ArrowRight');expect(page.locator('#tab-backup')).to_be_focused()
        expect(page.locator('#tab-backup')).to_have_attribute('aria-selected','true');expect(page.locator('#mode-backup')).to_be_visible()
        page.locator('#privacy-details').evaluate('(el)=>el.open=true')
        for copy in ['完整的單一已選官方 JSON','metadata','非當前分支','未選取的對話不會傳送','記憶體','不永久儲存','一般日誌','不是 Word']:
            expect(page.locator('#mode-backup')).to_contain_text(copy)
        page.keyboard.press('Home')  # Home outside the tablist is normal page navigation.
        page.locator('#tab-backup').focus();page.keyboard.press('Home');expect(page.locator('#tab-share')).to_be_focused()
        page.locator('#share-url').fill('https://chatgpt.com/c/private');page.keyboard.press('Enter')
        expect(page.locator('#share-error')).to_contain_text('私人對話網址不適用');expect(page.locator('#share-url')).to_have_attribute('aria-invalid','true')
        # Verify the shipped HTTPS default without contacting production; explicitly
        # clear it to exercise the still-supported unconfigured developer state.
        expect(page.locator('#api-base')).to_have_value('https://chatkeep.onrender.com')
        page.locator('#service-settings').evaluate('(el)=>el.open=true')
        page.locator('#api-base').fill('')
        page.locator('#share-url').fill('https://chatgpt.com/share/00000000-0000-0000-0000-000000000000');page.keyboard.press('Enter')
        expect(page.locator('#conversion-status')).to_contain_text('尚未設定');expect(page.locator('#service-settings')).to_have_attribute('open','')
        page.locator('#api-base').fill('http://public.example');expect(page.locator('#service-status')).to_contain_text('網址無效')
        page.locator('#api-base').fill('https://approved.example');expect(page.locator('#service-status')).to_contain_text('尚未驗證')
        self.assertFalse(self.external)
    def test_search_selection_filters_pages_empty_and_raw_json(self):
        page=self.open();data=self.scan(page)
        expect(page.locator('#results input')).to_have_count(50);expect(page.locator('#index-counts')).to_contain_text('總索引 365')
        page.locator('#results-next').click();expect(page.locator('#results-page')).to_contain_text('第 2 / 8 頁')
        page.locator('#select-visible').click();expect(page.locator('#count')).to_have_text('已選 365 段');expect(page.locator('#selected-results [role=listitem]')).to_have_count(25)
        page.locator('#search').fill('不會找到');expect(page.locator('#shown')).to_contain_text('沒有符合');expect(page.locator('#selection-scope')).to_contain_text('另有 365 段')
        page.locator('#reset-filters').click();page.locator('#deselect').click()
        page.locator('#advanced-filters').evaluate('(el)=>el.open=true');page.locator('#series').fill('系列');page.locator('#first').fill('1');page.locator('#last').fill('3')
        page.locator('#from').fill('2024-01-02');page.locator('#to').fill('2024-01-02')
        expect(page.locator('#results input')).to_have_count(3);expect(page.locator('#report')).to_contain_text('重複編號：1');expect(page.locator('#report')).to_contain_text('未找到編號：2')
        expect(page.locator('#report')).to_contain_text('成功解析');expect(page.locator('#report')).to_contain_text('節點數不等於可見訊息數')
        page.locator('#results input').first.check();page.locator('#results button').first.click();expect(page.locator('#preview')).to_be_focused()
        page.locator('#raw-download').evaluate('(el)=>el.open=true')
        with page.expect_download() as info:page.locator('#download').click()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'raw.json';info.value.save_as(path);self.assertEqual(json.loads(path.read_bytes()),data[0])
        expect(page.locator('#export-status')).to_contain_text('已啟動')
        page.locator('#reset').click();expect(page.locator('#progress')).to_contain_text('已清除')
    def test_viewports_long_titles_selection_and_accessible_controls(self):
        page=self.open();self.scan(page);page.locator('#select-visible').click();page.locator('#advanced-filters').evaluate('(el)=>el.open=true')
        for width in [320,390,768,844,1280]:
            page.set_viewport_size({'width':width,'height':390 if width==844 else 900});self.assert_layout(page)
        missing=page.evaluate('''()=>[...document.querySelectorAll('input,select')].filter(e=>!e.labels?.length&&!e.getAttribute('aria-label')).map(e=>e.id)''')
        self.assertFalse(missing)
        for id in ['progress','export-status','conversion-status','service-status','index-counts']:
            self.assertEqual(page.locator('#'+id).get_attribute('aria-live'),'polite')
        page.locator('#search').focus();self.assertEqual(page.locator('#search').evaluate('(e)=>getComputedStyle(e).outlineStyle'),'solid')
        page.keyboard.press('Tab');self.assertNotEqual(page.evaluate('document.activeElement.tagName'),'BODY')
    def test_queue_reports_download_release_xss_and_pagination(self):
        page=self.open(fake=True);self.start_fake(page)
        expect(page.locator('#conversion-results .job-card')).to_have_count(20)
        expect(page.locator('#queue-summary')).to_contain_text('失敗・可重試');expect(page.locator('#queue-summary')).to_contain_text('已釋放記憶體')
        card=page.locator('.job-card').first;expect(card.locator('h3')).to_have_text('1．'+TITLE)
        details=card.locator('details').last;expect(details).not_to_have_attribute('open','');details.locator('summary').click()
        expect(details).to_contain_text('normalized_output_sequence');expect(details).to_contain_text('不代表已與 ChatGPT 官方網頁逐字比對');expect(details).to_contain_text('SHA-256')
        with page.expect_download() as info:card.get_by_role('button',name='下載 DOCX').click()
        self.assertEqual(info.value.suggested_filename,'_CON.docx');expect(card).to_contain_text('已啟動下載（未確認是否保存至磁碟）')
        expect(details).to_have_attribute('open','');expect(card.get_by_role('button',name='下載 DOCX')).to_be_focused()
        self.assertIsNone(page.evaluate('window.PRIVATE_XSS'))
        for width in [320,390,768,844,1280]:page.set_viewport_size({'width':width,'height':900});self.assert_layout(page)
        card.get_by_role('button',name='釋放成果').click();expect(card).to_contain_text('成果已從本頁記憶體釋放');expect(card.locator('dl').first).to_contain_text('DOCX')
        page.locator('#queue-next').click();expect(page.locator('#queue-page')).to_contain_text('第 2 / 7 頁');expect(page.locator('.job-card')).to_have_count(20)
        page.locator('#cancel-conversion').click();expect(page.locator('#queue-summary')).to_contain_text('已取消')
        page.locator('#clear-conversion').click();expect(page.locator('#conversion-results')).to_be_empty()
    def test_retry_skip_cancel_states_and_focus_stability(self):
        page=self.open(fake=True);self.start_fake(page)
        retry=page.get_by_role('button',name='重試缺少批次（含失敗批次 2）');expect(retry).to_be_visible();retry.click()
        expect(page.locator('.job-card').nth(1)).to_contain_text('正在處理第 2 / 4 批');expect(page.locator('#conversion-title')).to_be_focused()
        expect(page.locator('#continue-conversion')).to_be_disabled()
        page.locator('#cancel-conversion').click();expect(page.locator('#conversion-status')).to_contain_text('已取消');expect(page.locator('.job-card').first.get_by_role('button',name='下載 DOCX')).to_be_visible()
        # New conversion cannot silently discard a retained result.
        page.locator('#share-url').fill('https://chatgpt.com/share/00000000-0000-0000-0000-000000000000');page.locator('#convert-share').click()
        expect(page.locator('#conversion-status')).to_contain_text('尚未釋放的成果')
        page.locator('#clear-conversion').click();self.start_fake(page)
        page.get_by_role('button',name='略過失敗對話').click();expect(page.locator('.job-card').nth(1)).to_contain_text('已略過')
    def test_worker_failure_during_conversion_keeps_cleanup_locked_and_restarts(self):
        page=self.open(init='''const BaseWorker=Worker;window.observedWorkers=[];
window.Worker=class extends BaseWorker{
 constructor(url,options){super(url,options);this.isIndex=String(url).endsWith('/worker.mjs');window.observedWorkers.push(this);}
 postMessage(message,...rest){if(this.isIndex&&message.type==='cancel'){window.cleanupStarted=true;setTimeout(()=>super.postMessage(message,...rest),1000);}else super.postMessage(message,...rest);}
};''')
        self.scan(page,3);page.locator('#results input').first.check()
        page.locator('#service-settings').evaluate('(el)=>el.open=true');page.locator('#api-base').fill(self.origin)
        held=[];page.route('**/api/convert-json',lambda route:held.append(route))
        page.locator('#convert-selected').click();page.wait_for_timeout(6600);self.assertTrue(held)
        page.evaluate('window.observedWorkers.find(w=>w.isIndex).onerror(new Event("error"))')
        page.wait_for_function('window.cleanupStarted===true');page.wait_for_timeout(100)
        expect(page.locator('#scan')).to_be_disabled();expect(page.locator('#files')).to_be_disabled()
        expect(page.locator('#progress')).to_contain_text('解析 Worker 停止',timeout=5000)
        expect(page.locator('#scan')).to_be_enabled()
        expect(page.locator('#conversion-results button:visible',has_text='下載')).to_have_count(0)
        for route in held:
            try:route.abort('aborted')
            except Exception:pass  # Native abort may already dispose the intercepted request.
        page.unroute('**/api/convert-json');self.scan(page,2)
        expect(page.locator('#index-counts')).to_contain_text('總索引 2')

    def test_service_errors_have_human_copy_and_optional_codes(self):
        page=self.open(fake=True);self.start_fake(page)
        for code,copy in [('API_UNAVAILABLE','尚未部署'),('API_INCOMPATIBLE','版本或回應'),('NETWORK_OR_CORS','來源白名單')]:
            page.evaluate('(code)=>{const q=window.testQueue,j=q.jobs[1];j.error=code;q.emit(j)}',code)
            expect(page.locator('#service-status')).to_contain_text(copy)
            expect(page.locator('.job-card').nth(1)).to_contain_text(copy)
        details=page.locator('.job-card').nth(1).locator('details:visible').first
        details.locator('summary').click();expect(details).to_contain_text('NETWORK_OR_CORS')

    def test_derived_details_are_separate_and_never_claim_official_source_verification(self):
        page=self.open(fake=True);self.start_fake(page)
        page.evaluate('''()=>{const q=window.testQueue,j=q.jobs[0];j.report={...j.report,source:'official_json_derived',integrity_basis:'browser_derived_sequence',client_source_counts:{raw_node_count:17,active_path_message_count:8,off_branch_node_count:2,skipped_categories:{hidden:2}}};j.partTotal=4;q.emit(j)}''')
        card=page.locator('.job-card').first;card.get_by_text('進階完整性資訊').click()
        expect(card).to_contain_text('browser_derived_sequence');expect(card).to_contain_text('伺服器只驗證各批，未驗證原始完整官方 JSON');expect(card).to_contain_text('隱藏訊息 2 項')
        self.assertIsNone(page.evaluate('window.PRIVATE_XSS'))


if __name__=='__main__':unittest.main(verbosity=2)
