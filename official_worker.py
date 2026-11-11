"""Private conversion subprocess: bounded stdin/stdout only; never writes files/logs."""
import json
import resource
import sys
from official_json import MAX_INPUT, OfficialError, normalize_official
from word_export import ExportError
from chatkeep import ExtractionError
from conversation_export import export_conversation, envelope


def classify_share_failure(exc):
    """Privacy-safe stage code for diagnosing anonymous public-share failures."""
    detail = str(exc)
    match = __import__('re').fullmatch(r'分享頁回應 HTTP ([1-5][0-9][0-9])；可能已失效或限制匿名存取', detail)
    if match:
        return 'SOURCE_HTTP_' + match.group(1)
    if any(x in detail for x in ('無法建立公開網路連線', '無法取得有效分享頁', '擷取逾時', '公開網路連線逾時')):
        return 'SOURCE_FETCH_FAILED'
    if any(x in detail for x in ('HTML exceeds permitted size', 'HTML 下載大小', 'HTML 下載不完整', '無效的下載大小')):
        return 'SOURCE_SIZE_OR_TRUNCATED'
    if any(x in detail for x in ('No ChatGPT stream found', 'Unterminated stream chunk', 'Malformed embedded stream chunk',
                                'Malformed or incomplete stream root', 'Unsupported deferred stream frame',
                                'Unsupported turbo-stream tag', 'Decoded stream contains no conversation object')):
        return 'SHARE_FORMAT_UNSUPPORTED'
    if any(x in detail for x in ('Cannot determine the active conversation branch', 'Active branch and linear conversation disagree',
                                'Broken conversation parent', 'Cyclic stream reference', 'Conversation node ID mismatch')):
        return 'CONVERSATION_STRUCTURE_FAILED'
    return 'EXTRACTION_VALIDATION_FAILED'


def archive_model(body):
    import base64
    import binascii
    from share_archive import extract_archive
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or set(payload) != {'filename', 'data'}:
            raise ValueError()
        name, encoded = payload['filename'], payload['data']
        if not isinstance(name, str) or len(name) > 150 or not isinstance(encoded, str):
            raise ValueError()
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, KeyError, binascii.Error) as exc:
        raise ExtractionError('ARCHIVE_INPUT_INVALID') from exc
    return extract_archive(data, name)


def readable_share(model, source='public_share'):
    messages = []
    for item in model.get('messages', []):
        if item.get('category') not in ('visible', 'non_text'):
            continue
        role = item.get('role')
        if role not in ('user', 'assistant'):
            continue
        value = item.get('text')
        if isinstance(value, str) and value.strip():
            messages.append({'role': role, 'text': value})
    if not messages:
        raise ExtractionError('No readable messages')
    return {'ok': True, 'data': {'title': model.get('title') or '公開分享對話',
        'messages': messages, 'report': {'source': source,
        'status': model.get('report', {}).get('status'),
        'warnings': model.get('report', {}).get('warnings', []),
        'issues': len(model.get('report', {}).get('issues', []))}}}


def result(body, mode='official'):
    if mode in ('archive_reader', 'archive_word'):
        model = archive_model(body)
        if mode == 'archive_reader':
            return readable_share(model, 'user_uploaded_archive')
        return envelope(export_conversation(model, 'share_link', None))
    if mode == 'share_reader':
        from chatkeep import extract_url, validate_url
        payload = json.loads(body)
        url = payload['url']
        validate_url(url)
        model = extract_url(url)
        return readable_share(model)
    if mode == 'chunk':
        from chunk_transfer import convert_chunk
        return convert_chunk(body)
    if mode == 'share':
        from chatkeep import extract_url, validate_url
        payload = json.loads(body)
        url = payload['url']; validate_url(url)
        model = extract_url(url)
        report = None
        source = 'share_link'
    else:
        model, report = normalize_official(body)
        source = 'official_json'
    return envelope(export_conversation(model, source, report))


def main():
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
        value = result(sys.stdin.buffer.read((17_000_000 if sys.argv[1:2] and sys.argv[1] in ('archive_reader', 'archive_word') else MAX_INPUT) + 1), sys.argv[1] if len(sys.argv)>1 else 'official')
        status = 200
    except OfficialError as exc:
        status, value = exc.status, {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
    except ExportError as exc:
        status, value = 422, {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
    except ExtractionError as exc:
        # Diagnostics contain only a fixed category; never expose URLs,
        # page contents, request values or exception strings.
        category = classify_share_failure(exc)
        status, value = 502, {'ok': False, 'error': {
            'code': 'EXTRACTION_FAILED',
            'message': '無法取得可安全解析的公開分享對話。',
            'stage': category,
        }}
    except MemoryError:
        status, value = 503, {'ok': False, 'error': {'code': 'RESOURCE_LIMIT', 'message': '轉換超過工作程序記憶體限制。'}}
    except Exception:
        status, value = 503, {'ok': False, 'error': {'code': 'CONVERSION_FAILED', 'message': '無法安全完成轉換。'}}
    sys.stdout.buffer.write(json.dumps({'status': status, 'value': value}, ensure_ascii=False, allow_nan=False).encode('utf-8'))


if __name__ == '__main__':
    main()
