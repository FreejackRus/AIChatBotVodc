"""Gunicorn settings for FastAPI and long-lived SSE responses."""

import os


bind = os.getenv("GUNICORN_BIND", "0.0.0.0:5000")
workers = int(os.getenv("MAX_WORKERS", "2"))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = int(os.getenv("GUNICORN_TIMEOUT", "90"))
graceful_timeout = 30
keepalive = 5
max_requests = 5000
max_requests_jitter = 250

accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
capture_output = True
preload_app = False
proc_name = "vodc-ai-navigator"

limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190
