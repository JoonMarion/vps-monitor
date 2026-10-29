"""Ubuntu production entry point. Nginx is the only public listener."""

bind = "unix:/run/vps-monitor/gunicorn.sock"
umask = 0o117
worker_tmp_dir = "/run/vps-monitor"
workers = 2
worker_class = "gthread"
threads = 4
timeout = 180
graceful_timeout = 30
keepalive = 5
max_requests = 1000
max_requests_jitter = 100
limit_request_fields = 50
limit_request_field_size = 4096
forwarded_allow_ips = "127.0.0.1"
accesslog = "-"
errorlog = "-"
# Log paths and timing, never request bodies, query strings or credentials.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'
capture_output = True
