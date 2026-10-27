"""Synthetic Word render/round-trip QA, optional LibreOffice or local Docker image.

Only synthetic previews may be retained via --output. No live data is used here.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docx import Document
from docx.oxml.ns import qn
from word_export import build_docx
from test_rich_word import model
from docx_helpers import document_text

SHOWCASE = '''# 語義與版面驗收
繁體中文標點，能搜尋、複製與編輯。
- 清單第一項
- 清單第二項
> 原生引用區塊
| 欄位 | 數值 |
| --- | --- |
| 合成名稱 | 123 |
<box><caption>巢狀資訊卡標籤</caption><row><col><text>左側欄位內容</text><card><text>次層完整正文</text></card></col><col><text>右側欄位內容</text></col></row></box>
LINE｜小明：19:30 左側合成訊息
LINE｜我：19:31 右側合成回覆
<button label="選擇方案甲"/><checkbox label="勾選選項乙"/>
```python
print("真正程式碼 <box>保留標記</box>")
```
公式：\\(x^2+y^2=z^2\\)
<AsyncImage query="合成圖片佔位"/>
<unknown>未知元件保留正文</unknown>
'''


def render_files(directory, image=None):
    files=[str(path) for path in directory.glob('*.docx')]
    if image:
        command=['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL',
                 '--security-opt','no-new-privileges','--user','1000:1000',
                 '--tmpfs','/tmp:rw,size=256m','--mount',f'type=bind,src={directory},dst=/data',image,
                 'libreoffice','-env:UserInstallation=file:///tmp/lo','--headless','--convert-to','pdf',
                 '--outdir','/data',*[f'/data/{Path(path).name}' for path in files]]
    else:
        executable=shutil.which('libreoffice') or shutil.which('soffice')
        if not executable:raise RuntimeError('LibreOffice unavailable; visual QA not performed')
        command=[executable,'-env:UserInstallation=file://'+str(directory/'profile'),'--headless','--convert-to','pdf','--outdir',str(directory),*files]
    subprocess.run(command,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)


def run(directory,image=None):
    for count in [4,100,1000]:
        source=model(SHOWCASE)
        source['messages']=[{'role':'user' if i%2 else 'assistant',
                             'text':SHOWCASE if i==0 else f'唯一標記{i:04d} 合成正文，保留順序與繁體中文。\n第二行可編輯。'} for i in range(count)]
        before=time.perf_counter();data=build_docx(source);elapsed=time.perf_counter()-before
        document=Document(BytesIO(data))
        output=document_text(document)
        markers=[f'唯一標記{i:04d}' for i in range(1,count)]
        assert all(output.count(marker)==1 for marker in markers)
        assert [output.index(marker) for marker in markers]==sorted(output.index(marker) for marker in markers)
        assert sum(p.style.name=='Heading 2' for p in document.paragraphs)==count
        (directory/f'synthetic-{count}.docx').write_bytes(data)
        print(json.dumps({'synthetic_messages':count,'seconds':round(elapsed,3),'bytes':len(data),'process_peak_mib':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1),'word_content_check':'passed'}))
    # One very long native card tests splitting rather than clipping after one page.
    long_source=model('<box><text>'+'\n'.join(f'長卡片標記{i:04d}，每一行都應在文件內。' for i in range(400))+'</text></box>')
    (directory/'synthetic-long-card.docx').write_bytes(build_docx(long_source))
    table_source=model('| 欄位 | 內容 |\n| --- | --- |\n'+'\n'.join(f'| 表格列標記{i:04d} | 合成跨頁內容 |' for i in range(180)))
    (directory/'synthetic-table.docx').write_bytes(build_docx(table_source))
    render_files(directory,image)
    import fitz
    for path in sorted(directory.glob('*.pdf')):
        with fitz.open(path) as pdf:
            text=''.join(page.get_text() for page in pdf)
            count=int(path.stem.split('-')[-1]) if path.stem.split('-')[-1].isdigit() else None
            expected=[f'唯一標記{i:04d}' for i in range(1,count)] if count else ([f'表格列標記{i:04d}' for i in range(180)] if path.stem=='synthetic-table' else [f'長卡片標記{i:04d}' for i in range(400)])
            # PDF text may insert spaces at font/script boundaries.
            compact=''.join(text.split())
            assert all(marker in compact for marker in expected), 'PDF clipped synthetic content'
            if count:
                assert '次層完整正文' in compact
                assert '小明' in compact and '19:30' in compact
            print(json.dumps({'pdf':path.name,'pages':len(pdf),'all_synthetic_markers_visible':True},ensure_ascii=False))
            if count==4:
                for index in range(len(pdf)):
                    pdf[index].get_pixmap(matrix=fitz.Matrix(1,1)).save(directory/f'preview-{index+1}.png')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--docker-image');parser.add_argument('--output',type=Path);args=parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True,exist_ok=True);run(args.output.resolve(),args.docker_image)
    else:
        with tempfile.TemporaryDirectory(prefix='chatkeep-visual-') as temporary:run(Path(temporary),args.docker_image)
