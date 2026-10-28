"""Private conversion subprocess: bounded stdin/stdout only; never writes files/logs."""
import json
import resource
import sys
from official_json import MAX_INPUT, OfficialError, normalize_official
from word_export import ExportError
from chatkeep import ExtractionError
from conversation_export import export_conversation, envelope


def result(body, mode='official'):
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
    except ExtractionError:
        status, value = 502, {'ok': False, 'error': {'code': 'EXTRACTION_FAILED', 'message': '無法取得可安全解析的公開分享對話。'}}
    except MemoryError:
        status, value = 503, {'ok': False, 'error': {'code': 'RESOURCE_LIMIT', 'message': '轉換超過工作程序記憶體限制。'}}
    except Exception:
        status, value = 503, {'ok': False, 'error': {'code': 'CONVERSION_FAILED', 'message': '無法安全完成轉換。'}}
    sys.stdout.buffer.write(json.dumps({'status': status, 'value': value}, ensure_ascii=False, allow_nan=False).encode('utf-8'))


if __name__ == '__main__':
    main()
