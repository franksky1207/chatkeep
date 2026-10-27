"""Basic editable Word export from the one normalized ChatKeep model."""
from io import BytesIO
import re
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from rich_word import render_message
from word_layout import configure, polish_tables


class ExportError(ValueError):
    pass


def filename_for(title):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', str(title)).strip(' .')[:100]
    name = name.encode('utf-8')[:200].decode('utf-8', errors='ignore').rstrip(' .')
    if not name:
        name = '未命名對話'
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])', name.split('.')[0].rstrip(' '), re.I):
        name = '_' + name
    return name + '.docx'


def _check_xml(text):
    if any(not (c in '\t\n\r' or '\x20' <= c <= '\ud7ff' or '\ue000' <= c <= '\ufffd' or '\U00010000' <= c <= '\U0010ffff') for c in text):
        raise ExportError('來源含 Word 無法保存的控制字元；未產生可能缺字的文件。')


def build_docx(model, rich=True, on_progress=None, on_pack=None, warnings_out=None):
    if model.get('schema_version') != '1.0' or not model.get('messages'):
        raise ExportError('沒有可匯出的標準化訊息。')
    messages = model['messages']
    if len(messages) > 5000 or sum(len(m['text']) for m in messages) > 5_000_000:
        raise ExportError('對話超過本版安全上限（5,000 則或 500 萬字元），未截斷或產生不完整文件。')
    if rich and sum(m['text'].count('\n') + m['text'].count('<') for m in messages) > 100000:
        raise ExportError('對話版面超過本版安全上限，未截斷內容；請使用原文匯出或縮小分享範圍。')
    document = configure(Document())
    title = str(model['title'])
    _check_xml(title)
    document.add_heading(title, 0)
    report = model['report']
    document.add_paragraph('ChatKeep｜對話收藏')
    document.add_paragraph('完整性：尚未完成逐訊息比對。可匯出訊息 %d 則。' % len(model['messages']))
    for warning in report['warnings']:
        _check_xml(warning)
        document.add_paragraph(warning)
    total_messages = len(model['messages'])
    rendering_warnings = []
    if on_progress:
        on_progress(0, total_messages)
    for number, message in enumerate(model['messages'], 1):
        role = {'user': '使用者', 'assistant': 'ChatGPT'}.get(message['role'], message['role'])
        document.add_heading('%d · %s' % (number, role), 2)
        text = message['text']
        _check_xml(text)
        # Raw Markdown/UI code is intentionally literal at stage 1-2. Word native
        # runs preserve editable text, tabs and line breaks, with no truncation.
        if rich:
            for warning in render_message(document, text):
                rendering_warnings.append({'message_index': number - 1, 'reason': warning})
                document.add_paragraph('［轉換警告］' + warning, style='ChatKeep Warning')
        else:
            document.add_paragraph().add_run(text)
        if message.get('category') == 'non_text':
            document.add_paragraph('［此訊息含未還原的非文字內容；以上保留可取得文字。］')
        if on_progress and (number % 10 == 0 or number == total_messages):
            on_progress(number, total_messages)
    polish_tables(document)
    if warnings_out is not None:
        warnings_out.extend(rendering_warnings)
    if on_pack:
        on_pack()
    data = BytesIO()
    document.save(data)
    if data.tell() > 16_000_000:
        raise ExportError('Word 超過 16 MB 下載上限；未提供截斷文件。')
    return data.getvalue()
