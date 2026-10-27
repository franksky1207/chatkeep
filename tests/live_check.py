"""Opt-in anonymous live verification; aggregate evidence only, no retained data.

Source/Word checks do not substitute for the missing research JSON or share DOM.
"""
import argparse
from collections import Counter
from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import time
import resource
import unicodedata
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docx import Document
from docx.oxml.ns import qn
from chatkeep import fetch_html, extract_stream, hydrate, find_conversation, parse_html
from semantic import parse, flatten
from word_export import build_docx
from visual_check import render_files

URL='https://chatgpt.com/share/6acdedca-cfa0-83ec-9622-dba167dfee84'
HAN=re.compile(r'[\u3400-\u9fff\U00020000-\U0003134f]')


def subsequence(expected,actual):
    iterator=iter(actual)
    return all(any(candidate==character for candidate in iterator) for character in expected)


def message_content(document):
    result=[];current=None
    for element in document.element.body:
        if element.tag==qn('w:p'):
            style=element.find('w:pPr/w:pStyle',element.nsmap)
            name=style.get(qn('w:val')) if style is not None else ''
            if name=='Heading2':
                current=[];result.append(current);continue
            if name=='ChatKeepWarning':continue
        if current is not None:
            current.extend(node.text or '' for node in element.iter(qn('w:t')))
    return [''.join(part) for part in result]


def run(visual=False,image=None):
    html=fetch_html(URL)
    conversation=find_conversation(hydrate(extract_stream(html)))
    model=parse_html(html,URL)
    raw=conversation['linear_conversation']
    assert len(model['records'])==len(raw)
    compared=0
    for node,record in zip(raw,model['records']):
        assert record['node_id']==node.get('id') and record['parent']==node.get('parent')
        source=node.get('message')
        if source is None:
            assert record['message'] is None;continue
        normalized=record['message']
        assert normalized['id']==source['id'] and normalized['role']==source['author']['role']
        assert normalized['create_time']==source.get('create_time')
        assert normalized['content']==source.get('content')
        content=source['content']
        if isinstance(content.get('text'),str):expected=content['text']
        else:expected='\n'.join(p if isinstance(p,str) else p['text'] for p in content.get('parts',[]) if isinstance(p,str) or isinstance(p,dict) and isinstance(p.get('text'),str))
        assert normalized['text']==expected
        assert normalized['text_sha256']==hashlib.sha256(expected.encode()).hexdigest()
        compared+=1
    assert dict(Counter(n['message']['author']['role'] for n in raw if n.get('message')))==model['report']['roles']
    raw_data=build_docx(model,rich=False)
    raw_doc=Document(BytesIO(raw_data))
    bodies=[p.text for i,p in enumerate(raw_doc.paragraphs) if i and raw_doc.paragraphs[i-1].style.name=='Heading 2']
    assert bodies==[m['text'] for m in model['messages']]
    warnings=[];started=time.perf_counter();rich_data=build_docx(model,warnings_out=warnings)
    render_seconds=time.perf_counter()-started
    peak_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    rich_doc=Document(BytesIO(rich_data));rendered=message_content(rich_doc)
    assert len(rendered)==len(model['messages'])
    code_count=0;projections=[];mismatches=[]
    paragraphs=[p.text for p in rich_doc.paragraphs]
    for index,(message,output) in enumerate(zip(model['messages'],rendered)):
        nodes,_=parse(message['text'])
        expected=''.join(flatten(node) for node in nodes)
        projections.append(expected)
        expected_han=HAN.findall(expected);actual_han=HAN.findall(output)
        if not subsequence(expected_han,actual_han):mismatches.append(index)
        for node in nodes:
            if node.kind=='code':
                assert node.text in paragraphs
                code_count+=1
    assert not mismatches,'Rich Word ordered Chinese-text coverage failed at message indices: '+str(mismatches)
    # Counts explain the previously observed 732/720 arithmetic without using
    # any expected count as a classifier or pretending to possess the reference.
    hidden_text=Counter();tool_code=0
    for record in model['records']:
        message=record['message']
        if not message:continue
        if record['category']=='hidden' and message['text'].strip():hidden_text[message['role']]+=1
        if record['category']=='tool_call' and message['content_type']=='code':tool_code+=1
    evidence={'http':'200 HTML','html_bytes':len(html.encode()),'source_records_compared':compared,
              'report':model['report'],'excluded_hidden_text':dict(hidden_text),'excluded_tool_code':tool_code,
              'raw_word_bytes':len(raw_data),'rich_word_bytes':len(rich_data),'word_messages_checked':len(rendered),
              'rich_ordered_chinese_coverage':'passed','literal_code_blocks_checked':code_count,
              'rendering_warnings':len(warnings),'rich_render_seconds':round(render_seconds,3),'process_peak_mib_before_pdf':round(peak_mib,1),'research_json_comparison':'尚未完成逐訊息比對'}
    if visual:
        import fitz
        with tempfile.TemporaryDirectory(prefix='chatkeep-private-') as temporary:
            directory=Path(temporary)
            (directory/'live.private.docx').write_bytes(rich_data)
            render_files(directory,image)
            with fitz.open(directory/'live.private.pdf') as pdf:
                output=''.join(page.get_text() for page in pdf)
                # Parallel cells have a visual reading order different from a PDF
                # extractor's span order. DOCX order was checked per message above;
                # here every OOXML Chinese character must survive actual rendering.
                expected=''.join(node.text or '' for node in rich_doc.element.body.iter(qn('w:t')))
                missing=Counter(HAN.findall(unicodedata.normalize('NFKC',expected)))-Counter(HAN.findall(unicodedata.normalize('NFKC',output)))
                if missing:
                    headings=list(re.finditer(r'(?:^|\n)(\d+)\s*·\s*(?:ChatGPT|使用者)',output))
                    gaps=[]
                    for i,heading in enumerate(headings):
                        number=int(heading.group(1))
                        if 1 <= number <= len(rendered):
                            end=headings[i+1].start() if i+1<len(headings) else len(output)
                            deficit=Counter(HAN.findall(rendered[number-1]))-Counter(HAN.findall(output[heading.end():end]))
                            if deficit:gaps.append({'message_index':number-1,'missing_character_count':sum(deficit.values())})
                    # Aggregate locations only, never source text or codepoints.
                    print(json.dumps({'pdf_missing_characters':sum(missing.values()),'pdf_heading_count':len(headings),'gaps':gaps}),file=sys.stderr)

                assert not missing, 'Live PDF clipped Chinese characters'
                evidence['libreoffice_pdf']={'pages':len(pdf),'chinese_character_coverage':'passed',
                                             'source_order':'verified_per_message_in_docx'}
                assert all(abs(page.rect.width-595.28)<2 and abs(page.rect.height-841.89)<2 for page in pdf)
    print(json.dumps(evidence,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--visual',action='store_true');parser.add_argument('--docker-image');args=parser.parse_args()
    # Fail without dumping source content, file names or derived Word text.
    try:run(args.visual,args.docker_image)
    except Exception as error:
        print('Live verification failed ('+type(error).__name__+'); no conversation data logged.',file=sys.stderr)
        raise SystemExit(1)
