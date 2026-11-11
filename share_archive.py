"""Explicit user-provided Safari Web Archive / HTML import; no remote fetch.

Only the main HTML resource is used. Never open URLs, parse scripts or unpack
subresources. Reject untrusted archive formats and excessive content.
"""
import plistlib
from chatkeep import ExtractionError, parse_html, validate_url

MAX_ARCHIVE = 12_000_000
MAX_HTML = 9_000_000


def extract_archive(data, name=''):
    if not isinstance(data, bytes) or not data or len(data) > MAX_ARCHIVE:
        raise ExtractionError('ARCHIVE_SIZE_INVALID')
    name = name.lower()
    if name.endswith('.webarchive'):
        try:
            archive = plistlib.loads(data)
        except (ValueError, TypeError, OverflowError, plistlib.InvalidFileException) as exc:
            raise ExtractionError('ARCHIVE_INVALID') from exc
        if not isinstance(archive, dict):
            raise ExtractionError('ARCHIVE_INVALID')
        main = archive.get('WebMainResource')
        if not isinstance(main, dict):
            raise ExtractionError('ARCHIVE_INVALID')
        url = main.get('WebResourceURL')
        mime = main.get('WebResourceMIMEType')
        html_data = main.get('WebResourceData')
        if not isinstance(mime, str) or mime.lower() != 'text/html':
            raise ExtractionError('ARCHIVE_NOT_HTML')
    elif name.endswith(('.html', '.htm')):
        url = ''
        html_data = data
    else:
        raise ExtractionError('ARCHIVE_TYPE_INVALID')
    if url:
        validate_url(url)
    if not isinstance(html_data, bytes) or not 0 < len(html_data) <= MAX_HTML:
        raise ExtractionError('ARCHIVE_HTML_SIZE_INVALID')
    try:
        html = html_data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ExtractionError('ARCHIVE_HTML_ENCODING_INVALID') from exc
    # Strict parser requires original ChatGPT stream data. No DOM text
    # guessing, no silent partial results, no external resource fetch.
    model = parse_html(html, url)
    model['provenance'] = {'source': 'user_uploaded_archive', 'verified_against_live_page': False}
    return model
