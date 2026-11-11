"""Private conversion subprocess: bounded stdin/stdout only; never writes files/logs."""
import json
import resource
import sys
from official_json import MAX_INPUT, OfficialError, normalize_official
from word_export import ExportError
from chatkeep import ExtractionError
from conversation_export import export_conversation, envelope


def classify_share_failure(exc):
    """Return only fixed diagnostic codes; never expose source HTML or share URLs."""
    detail = str(exc)
    import re
    match = re.fullmatch(r'分享頁回應 HTTP ([1-5][0-9][0-9])；可能已失效或限制匿名存取', detail)
    if match:
        return 'SOURCE_HTTP_' + match.group(1)
    if 'No ChatGPT stream found' in detail or 'Unsupported turbo-stream tag' in detail:
        return 'SHARE_FORMAT_UNSUPPORTED'
    if 'active conversation branch' in detail or 'conversation disagree' in detail:
        return 'CONVERSATION_STRUCTURE_FAILED'
    if 'HTML exceeds permitted size' in detail or 'HTML 下載不完整' in detail:
        return 'SOURCE_SIZE_OR_TRUNCATED'
    if '擷取逾時' in detail:
        return 'SOURCE_TIMEOUT'
    return 'EXTRACTION_VALIDATION_FAILED'


def result(body, mode='official'):
    if mode == 'share_reader':
        from chatkeep import extract_url, validate_url
        payload = json.loads(body)
        url = payload['url']
        validate_url(url)
        model = extract_url(url)
        # Return only the published conversational text. No DOCX export.
        messages = []
        for item in model.get('messages', []):
            if item.get('category') not in ('visible', 'non_text'):
                continue
            role = item.get('role')
            if role not in ('user', 'assistant'):
                continue
            text = item.get('text')
            if isinstance(text, str) and text.strip():
                messages.append({'role': role, 'text': text})
        if not messages:
            raise ExtractionError('No readable messages')
        return {'ok': True, 'data': {'title': model.get('title') or '公開分享對話',
            'messages': messages, 'report': {'source': 'public_share',
            'status': model.get('report', {}).get('status'),
            'warnings': model.get('report', {}).get('warnings', []),
            'issues': len(model.get('report', {}).get('issues', []))}}}
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
        value = result(sys.stdin.buffer.read(MAX_INPUT + 1), sys.argv[1] if len(sys.argv)>1 else 'official')
        status = 200
    except OfficialError as exc:
        status, value = exc.status, {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
    except ExportError as exc:
        status, value = 422, {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
    except ExtractionError as exc:
        status, value = 502, {'ok': False, 'error': {
            'code': 'EXTRACTION_FAILED',
            'message': '無法取得可安全解析的公開分享對話。',
            'stage': classify_share_failure(exc)
        }}
    except MemoryError:
        status, value = 503, {'ok': False, 'error': {'code': 'RESOURCE_LIMIT', 'message': '轉換超過工作程序記憶體限制。'}}
    except Exception:
        status, value = 503, {'ok': False, 'error': {'code': 'CONVERSION_FAILED', 'message': '無法安全完成轉換。'}}
    sys.stdout.buffer.write(json.dumps({'status': status, 'value': value}, ensure_ascii=False, allow_nan=False).encode('utf-8'))


if __name__ == '__main__':
    main()
