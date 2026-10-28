"""Private conversion subprocess: bounded stdin/stdout only; never writes files/logs."""
import base64
import json
import resource
import sys
from official_json import MAX_INPUT, OfficialError, normalize_official
from word_export import build_docx, filename_for, ExportError


def result(body):
    model, report = normalize_official(body)
    warnings = []
    data = build_docx(model, rich=True, warnings_out=warnings)
    # Rendering warning reasons come from the shared renderer, not source text.
    if warnings:
        report['status'] = 'converted_with_warnings'
        report['warnings'].append({'code': 'RENDERING_LIMITATIONS', 'count': len(warnings),
                                   'message': '部分格式以原文或警告保留，詳見 Word 內註記。'})
    return {'ok': True, 'filename': filename_for(model['title']),
            'mime_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'document': base64.b64encode(data).decode('ascii'), 'report': report}


def main():
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
        value = result(sys.stdin.buffer.read(MAX_INPUT + 1))
        status = 200
    except OfficialError as exc:
        status, value = exc.status, {'ok': False, 'error': {'code': exc.code, 'message': str(exc)}}
    except ExportError:
        status, value = 422, {'ok': False, 'error': {'code': 'EXPORT_LIMIT', 'message': 'Word 格式或輸出超過安全限制，未提供截斷文件。'}}
    except Exception:
        status, value = 503, {'ok': False, 'error': {'code': 'CONVERSION_FAILED', 'message': '無法安全完成轉換。'}}
    sys.stdout.buffer.write(json.dumps({'status': status, 'value': value}, ensure_ascii=False, allow_nan=False).encode('utf-8'))


if __name__ == '__main__':
    main()
