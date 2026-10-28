import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const b=await chromium.launch();
const page=await b.newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:8765/',{waitUntil:'networkidle'});
assert.equal(await page.locator('#tab-backup').getAttribute('aria-selected'),'true');
assert.equal(await page.locator('#service-internals').isVisible(),false);
assert.equal(await page.locator('#conversion-panel').isVisible(),false);
const nodes={
  a:{id:'a',parent:null,children:['b'],message:{author:{role:'user'},content:{content_type:'text',parts:['校慶開始']}}},
  b:{id:'b',parent:'a',children:[],message:{author:{role:'assistant'},content:{content_type:'text',parts:['# 校慶活動\n**班級**\n| 項目 | 內容 |\n|---|---|\n| 展示 | 海報 |\n- 第一項']}}}
};
const json=JSON.stringify([{title:'HTML 測試對話',current_node:'b',mapping:nodes}]);
await page.locator('#files').setInputFiles({name:'conversations-000.json',mimeType:'application/json',buffer:Buffer.from(json)});
await page.locator('#scan').click();
await page.locator('#picker').waitFor({state:'visible',timeout:30000});
await page.getByRole('button',{name:'閱讀對話'}).click();
await page.locator('#reader-messages article').first().waitFor({timeout:30000});
assert.equal(await page.locator('#reader-messages article').count(),2);
assert.equal(await page.locator('.reader-body table').count(),1);
assert.equal(await page.locator('.reader-body strong').count(),1);
await page.locator('#reader-search').fill('校慶');
await page.getByText('符合的訊息 2 則').waitFor({timeout:10000});
assert.match(await page.locator('#results').innerText(),/MB/);
await page.locator('#reader-close').click();
assert.equal(await page.locator('#reader-panel').isVisible(),false);
await page.locator('#tab-share').click();
assert.equal(await page.locator('#mode-share').isVisible(),true);
assert.deepEqual(errors,[]);
console.log('PASS: real Chromium smoke');
await b.close();
