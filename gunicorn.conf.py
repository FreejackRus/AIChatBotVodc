# Конфигурация Gunicorn для чатбота ВОККДЦ

# Настройки сети
bind = "0.0.0.0:8085"
backlog = 2048

# Настройки воркеров
workers = 4  # Количество воркеров (CPU cores * 2 + 1)
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 50

# Настройки безопасности
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# Настройки логирования
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Настройки процесса
daemon = False
pidfile = "gunicorn.pid"
user = None
group = None
tmp_upload_dir = None

# Настройки SSL (раскомментируйте при необходимости)
# keyfile = "/path/to/key.pem"
# certfile = "/path/to/cert.pem"

# Настройки для продакшена
preload_app = True
reload = False
spew = False

# Настройки имени процесса
proc_name = "vodc-chatbot"

# Настройки таймаутов graceful restart
graceful_timeout = 30