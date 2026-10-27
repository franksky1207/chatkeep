"""Basic editable Word export from the one normalized ChatKeep model."""
from io import BytesIO
import re
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


class ExportError(ValueError):
    pass


def filename_for(title):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', str(title)).strip(' .')[:100]
    if not name:
        name = '未命名對話'
    if name.upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(10)), *(f'LPT{i}' for i in range(10))}:
        name = '_' + name
    return name + '.docx'


def _check_xml(text):
    if any(not (c in '\t\n\r' or '\x20' <= c <= '\ud7ff' or '\ue000' <= c <= '\ufffd' or '\U00010000' <= c <= '\U0010ffff') for c in text):
        raise ExportError('來源含 Word 無法保存的控制字元；未產生可能缺字的文件。')


def build_docx(model):
    if model.get('schema_version') != '1.0' or not model.get('messages'):
        raise ExportError('沒有可匯出的標準化訊息。')
    document = Document()
    style = document.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = Pt(11)
    fonts = style.element.get_or_add_rPr()
    east_asia = OxmlElement('w:rFonts')
    east_asia.set(qn('w:eastAsia'), 'Microsoft JhengHei')
    fonts.append(east_asia)
    title = str(model['title'])
    _check_xml(title)
    document.add_heading(title, 0)
    report = model['report']
    document.add_paragraph('ChatKeep｜對話收藏')
    document.add_paragraph('完整性：尚未完成逐訊息比對。可匯出訊息 %d 則。' % len(model['messages']))
    for warning in report['warnings']:
        _check_xml(warning)
        document.add_paragraph(warning)
    for number, message in enumerate(model['messages'], 1):
        role = {'user': '使用者', 'assistant': 'ChatGPT'}.get(message['role'], message['role'])
        document.add_heading('%d · %s' % (number, role), 2)
        text = message['text']
        _check_xml(text)
        # Raw Markdown/UI code is intentionally literal at stage 1-2. Word native
        # runs preserve editable text, tabs and line breaks, with no truncation.
        document.add_paragraph().add_run(text)
        if message.get('category') == 'non_text':
            document.add_paragraph('［此訊息含未還原的非文字內容；以上保留可取得文字。］')
    data = BytesIO()
    document.save(data)
    return data.getvalue()
