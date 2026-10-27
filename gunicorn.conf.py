"""One bounded process for the proposed 512 MB free service; no access logs."""
import os
os.environ.setdefault('CHATKEEP_MAX_CONCURRENT', '1')
bind = '0.0.0.0:' + str(int(os.environ.get('PORT', '10000')))
workers = 1
worker_class = 'gthread'
threads = 8
timeout = 100
graceful_timeout = 100
keepalive = 2
max_requests = 100
max_requests_jitter = 10
limit_request_line = 4096
limit_request_fields = 30
limit_request_field_size = 4096
forwarded_allow_ips = ''
secure_scheme_headers = {}
accesslog = None
errorlog = '-'
loglevel = 'warning'
