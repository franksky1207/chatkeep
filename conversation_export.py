"""Shared DOCX-first, whole-message rollover and transactional in-memory ZIP."""
import base64
import gc
import hashlib
from io import BytesIO
import json
from zipfile import ZipFile, ZIP_STORED
from lxml import etree
from docx.oxml.ns import qn
from export_limits import CAPACITY, DOCX_MIME, MAX_VOLUMES, supported_text_content
from word_export import (ExportError, VolumeFull, WordVolume, LimitedBuffer, filename_for, validate_model)


def digest(messages):
    value = hashlib.sha256()
    for message in messages:
        encoded = json.dumps([message.get('id'), message['role'], message['text']],
                             ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        value.update(len(encoded).to_bytes(8, 'big')); value.update(encoded)
    return value.hexdigest()


def verify_docx(data, first, last):
    # Small bounded document XML; confirm the serialized message ledger, not just loop counters.
    with ZipFile(BytesIO(data)) as archive:
        if archive.testzip() is not None: raise ExportError('文件封裝驗證失敗。', 'INTEGRITY_FAILED')
        root = etree.fromstring(archive.read('word/document.xml'), etree.XMLParser(resolve_entities=False, no_network=True))
    markers = [n.get(qn('w:name')) for n in root.iter(qn('w:bookmarkStart'))
               if n.get(qn('w:name'), '').startswith('ChatKeepMessage_')]
    if markers != ['ChatKeepMessage_%d' % n for n in range(first, last+1)]:
        raise ExportError('文件訊息順序驗證失敗。', 'INTEGRITY_FAILED')
    for cell in root.iter(qn('w:tc')):
        if cell[-1].tag != qn('w:p'):
            raise ExportError('Word 表格結構驗證失敗。', 'INTEGRITY_FAILED')


def export_conversation(model, source, source_report=None, capacity=CAPACITY, allow_zip=True,
                        on_progress=None, on_pack=None, check=None, strict=True, rich=True, warnings_out=None):
    validate_model(model)
    messages = model['messages']; total = len(messages)
    if strict and (any(m.get('category') == 'non_text' or 'content' in m and not supported_text_content(m['content']) for m in messages) or
                   any(i.get('reason') in ('unsupported_content', 'unfinished_message') for i in model['report'].get('issues', []))):
        raise ExportError('有效對話含未支援或未完成內容，未提供部分文件。', 'UNSUPPORTED_CONTENT')
    report = dict(source_report or {})
    warnings = list(report.get('warnings', []))
    if source == 'share_link':
        mapping_source = model.get('branch', {}).get('source') == 'current_node_parent_chain'
        report.update(raw_node_count=model['report'].get('total_mapping_nodes') if mapping_source else None,
                      active_path_message_count=model['report'].get('raw_messages'),
                      source='share_link', reference_comparison='not_performed')
        warnings.append({'code': 'SOURCE_UNVERIFIED', 'message': '依正規化有效輸出序列核對，未與原始網頁逐訊息比對。'})
        report['skipped_categories'] = {k:v for k,v in model['report'].get('categories', {}).items() if k not in ('visible', 'non_text')}
        for category, count in report['skipped_categories'].items():
            if count: warnings.append({'code':'SKIPPED_'+category.upper(), 'count':count, 'message':'已依規則略過非輸出節點。'})
        report['off_branch_node_count'] = model['report'].get('off_branch_nodes')
        if report['off_branch_node_count']:
            warnings.append({'code':'OFF_BRANCH_EXCLUDED', 'count':report['off_branch_node_count'], 'message':'非當前分支未輸出。'})
        if not strict and model['report'].get('issues'):
            warnings.append({'code':'LEGACY_SOURCE_LIMITATIONS', 'count':len(model['report']['issues']), 'message':'沿用舊版來源限制及部分內容警告；完整性僅指正規化輸出序列。'})
    parts, cursor = [], 0
    output = None
    archive = None
    if on_progress: on_progress(0, total)
    rendering_count = 0
    try:
        while cursor < total:
            if check: check()
            if len(parts) >= MAX_VOLUMES:
                raise ExportError('分卷數超過 16 卷資源限制。', 'VOLUME_LIMIT')
            volume = WordVolume(model, rich=rich, capacity=capacity, check=check)
            first = cursor
            while cursor < total:
                try: volume.add(cursor)
                except VolumeFull as exc:
                    if cursor == first:
                        raise ExportError('單則訊息超過安全 Word 結構容量，不能從訊息中切割。', 'MESSAGE_TOO_LARGE') from exc
                    if not allow_zip:
                        raise ExportError('此對話需要分卷，請使用支援 DOCX／ZIP 的新版 API。', 'MULTIPART_REQUIRED') from exc
                    break
                cursor += 1
                if on_progress and (cursor % 10 == 0 or cursor == total): on_progress(cursor, total)
            multipart = bool(parts) or cursor < total
            number = len(parts)+1
            data = volume.pack(number, multipart, on_pack)
            verify_docx(data, first+1, cursor)
            entry = {'number': number, 'first_message': first+1, 'last_message': cursor,
                     'message_count': cursor-first, 'sequence_sha256': digest(messages[first:cursor]),
                     'docx_bytes': len(data), 'structure': {'elements': volume.stats[0],
                      'xml_bytes': volume.stats[1], 'table_cells': volume.stats[2]}}
            rendering_count += len(volume.warnings)
            if warnings_out is not None: warnings_out.extend(volume.warnings)
            if multipart:
                # Suffix is appended AFTER sanitization/truncation so volume numbers cannot disappear.
                stem = filename_for(model['title'])[:-5]
                entry['filename'] = stem + '_第%d卷.docx' % number
                if archive is None:
                    output = LimitedBuffer()
                    archive = ZipFile(output, 'w', compression=ZIP_STORED, allowZip64=False)
                archive.writestr(entry['filename'], data)
            else:
                entry['filename'] = filename_for(model['title'])
                output = data
            parts.append(entry)
            # python-docx uses cyclic part references. Collect between volumes;
            # never retain all Word object graphs or all DOCX byte buffers.
            del volume, data
            gc.collect()
        if archive is not None:
            archive.close(); archive = None
            output = output.getvalue()
            with ZipFile(BytesIO(output)) as zipped:
                if zipped.namelist() != [p['filename'] for p in parts] or zipped.testzip() is not None:
                    raise ExportError('分卷 ZIP 驗證失敗。', 'INTEGRITY_FAILED')
        expected = 1
        for part in parts:
            if part['first_message'] != expected or part['last_message']-part['first_message']+1 != part['message_count']:
                raise ExportError('分卷範圍不連續。', 'INTEGRITY_FAILED')
            expected = part['last_message']+1
        if expected != total+1:
            raise ExportError('分卷訊息數不一致。', 'INTEGRITY_FAILED')
        if rendering_count:
            warnings.append({'code': 'RENDERING_LIMITATIONS', 'count': rendering_count,
                             'message': '部分格式以原文或警告保留，詳見 Word 內註記。'})
        report.update(source=source, expected_output_message_count=total, output_message_count=total,
                      docx_volume_count=len(parts), volumes=parts, warnings=warnings,
                      complete=True, truncated=False, duplicated=False, missing=False,
                      sequence_sha256=digest(messages), integrity_basis='normalized_output_sequence',
                      status='converted_with_warnings' if warnings else 'converted')
        return {'artifact_type': 'zip' if len(parts)>1 else 'docx',
                'filename': filename_for(model['title'])[:-5]+'_完整對話.zip' if len(parts)>1 else filename_for(model['title']),
                'mime_type': 'application/zip' if len(parts)>1 else DOCX_MIME,
                'data': output, 'report': report}
    finally:
        try:
            if archive is not None: archive.close()
        finally:
            if isinstance(output, LimitedBuffer): output.close()
        # No temporary directory, files or persistent conversation storage.


def envelope(artifact):
    return {'ok': True, 'api_version': 2, 'artifact_type': artifact['artifact_type'],
            'filename': artifact['filename'], 'mime_type': artifact['mime_type'],
            'document': base64.b64encode(artifact['data']).decode('ascii'), 'report': artifact['report']}
