"""Explicit browser origin policy; anonymous limits remain the abuse boundary."""
import os
import logging
from urllib.parse import urlsplit


def canonical_origin(value):
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            return None
        parsed.port
        return value if value == parsed.scheme + '://' + parsed.netloc else None
    except (ValueError, TypeError):
        return None


def allowed_origin(env):
    origin = env.get('HTTP_ORIGIN')
    if not origin:
        return env.get('HTTP_SEC_FETCH_SITE') != 'cross-site'
    if not canonical_origin(origin):
        return False
    same = env.get('wsgi.url_scheme', 'http') + '://' + env.get('HTTP_HOST', '')
    approved = {x.strip() for x in os.environ.get('CHATKEEP_ALLOWED_ORIGINS', '').split(',')
                if canonical_origin(x.strip())}
    return origin == same or origin in approved


def preflight_denial(env):
    """Fixed classifications only; Host must already have been checked."""
    if not env.get('HTTP_ORIGIN') or not allowed_origin(env):
        return 'ORIGIN_FORBIDDEN'
    if env.get('HTTP_COOKIE') or env.get('HTTP_AUTHORIZATION'):
        return 'PREFLIGHT_CREDENTIALS_FORBIDDEN'
    if env.get('HTTP_ACCESS_CONTROL_REQUEST_METHOD') != 'POST':
        return 'PREFLIGHT_METHOD_FORBIDDEN'
    requested = {x.strip().lower() for x in env.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS', '').split(',') if x.strip()}
    if not requested <= {'content-type'}:
        return 'PREFLIGHT_HEADERS_FORBIDDEN'
    return None


def preflight_diagnostic(code):
    """No request values, route, URL, credentials or content reach the logger."""
    if code not in {'HOST_FORBIDDEN', 'ORIGIN_FORBIDDEN',
                    'PREFLIGHT_METHOD_FORBIDDEN', 'PREFLIGHT_HEADERS_FORBIDDEN',
                    'PREFLIGHT_CREDENTIALS_FORBIDDEN'}:
        raise ValueError('Invalid preflight classification')
    logging.getLogger('chatkeep.cors').warning('chatkeep_preflight_denied status=403 code=%s', code)
    return [('X-ChatKeep-Preflight', code)]


def cors_headers(env):
    headers = [('Vary', 'Origin')]
    if env.get('HTTP_ORIGIN') and allowed_origin(env):
        headers += [('Access-Control-Allow-Origin', env['HTTP_ORIGIN']),
                    ('Access-Control-Expose-Headers', 'Retry-After')]
    return headers
