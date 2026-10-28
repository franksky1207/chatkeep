"""Explicit browser origin policy; anonymous limits remain the abuse boundary."""
import os
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


def cors_headers(env):
    headers = [('Vary', 'Origin')]
    if env.get('HTTP_ORIGIN') and allowed_origin(env):
        headers += [('Access-Control-Allow-Origin', env['HTTP_ORIGIN']),
                    ('Access-Control-Expose-Headers', 'Retry-After')]
    return headers
