# Руководство по развертыванию чатбота ВОККДЦ

## Архитектура решения

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Веб-интерфейс │    │  Flask-сервер    │    │   RAG-система   │
│   (HTML/CSS/JS) │◄──►│  (widget_server) │◄──►│ (rag_system.py) │
│                 │    │                  │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
       ▲                        │                        │
       │                        ▼                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  1С-Битрикс     │    │  Знания ВОККДЦ  │    │  Модель LLM     │
│  (PHP-компонент)│    │ (vodc_complete) │    │ (Ollama)        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Быстрый старт

### 1. Подготовка окружения
```bash
# Клонируйте репозиторий
git clone <repository-url>
cd AIChatBotVodc

# Создайте виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# или
.venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt
pip install flask flask-cors gunicorn
```

### 2. Запуск RAG-системы
```bash
# Запустите Ollama с API на порту 11434
# Убедитесь, что модель загружена и работает

# Проверьте работу RAG-системы
python demo_rag.py
```

### 3. Запуск веб-сервера
```bash
# Запуск в режиме разработки
python widget_server.py

# Для продакшена используйте gunicorn
gunicorn widget_server:app -c gunicorn.conf.py
```

### 4. Интеграция с 1С-Битрикс
Скопируйте компонент из `bitrix_integration/` в ваш сайт на 1С-Битрикс.

## Детальная настройка

### Настройка Ollama
1. Установите Ollama
2. Загрузите модель (например, Llama 3.2 3B)
3. Запустите Ollama сервер
4. Проверьте доступность: `curl http://localhost:11434/api/tags`

### Конфигурация Flask-сервера

Создайте файл `.env` в корне проекта:
```
FLASK_HOST=0.0.0.0
FLASK_PORT=8085
FLASK_DEBUG=False
OLLAMA_URL=http://localhost:11434
CORS_ORIGINS=*
```

### Настройка RAG-системы

Проверьте файл `knowledge_base/vodc_complete_info.md` - он должен содержать актуальную информацию о ВОККДЦ.

### Настройка CORS для продакшена

В `widget_server.py` обновите CORS-настройки:
```python
CORS(app, origins=["https://your-domain.com", "https://www.your-domain.com"])
```

## Развертывание на сервере

### Опция 1: Docker (рекомендуется)

Создайте `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8085

CMD ["gunicorn", "widget_server:app", "-c", "gunicorn.conf.py"]
```

Создайте `docker-compose.yml`:
```yaml
version: '3.8'
services:
  vodc-chatbot:
    build: .
    ports:
      - "8085:8085"
    environment:
      - FLASK_HOST=0.0.0.0
      - FLASK_PORT=8085
      - OLLAMA_URL=http://host.docker.internal:11434
    volumes:
      - ./knowledge_base:/app/knowledge_base
    restart: unless-stopped
```

Запустите:
```bash
docker-compose up -d
```

### Опция 2: Systemd-сервис

Создайте файл `/etc/systemd/system/vodc-chatbot.service`:
```ini
[Unit]
Description=VODC Chatbot Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/vodc-chatbot
Environment="PATH=/opt/vodc-chatbot/.venv/bin"
ExecStart=/opt/vodc-chatbot/.venv/bin/gunicorn widget_server:app -c gunicorn.conf.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Включите сервис:
```bash
sudo systemctl enable vodc-chatbot
sudo systemctl start vodc-chatbot
```

### Опция 3: Nginx + Gunicorn

Настройте nginx:
```nginx
server {
    listen 80;
    server_name chatbot.your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8085;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    location /static {
        alias /opt/vodc-chatbot/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

## Мониторинг и логирование

### Настройка логирования

В `widget_server.py` добавьте:
```python
import logging
from logging.handlers import RotatingFileHandler

# Настройка логирования
handler = RotatingFileHandler('logs/chatbot.log', maxBytes=10000000, backupCount=5)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

app.logger.addHandler(handler)
```

### Мониторинг с помощью systemd
```bash
# Просмотр статуса
sudo systemctl status vodc-chatbot

# Просмотр логов
sudo journalctl -u vodc-chatbot -f

# Перезапуск
sudo systemctl restart vodc-chatbot
```

### Health-check
Проверьте работоспособность:
```bash
curl http://localhost:8085/health
```

## Обновление системы

### Обновление RAG-системы
1. Обновите файл `knowledge_base/vodc_complete_info.md`
2. Перезапустите сервер: `sudo systemctl restart vodc-chatbot`

### Обновление кода
```bash
# Остановите сервис
sudo systemctl stop vodc-chatbot

# Обновите код
git pull origin main

# Перезапустите сервис
sudo systemctl start vodc-chatbot
```

## Резервное копирование

### Автоматическое резервное копирование
Создайте скрипт `/opt/backup-vodc-chatbot.sh`:
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
tar -czf /backup/vodc-chatbot-$DATE.tar.gz /opt/vodc-chatbot
find /backup -name "vodc-chatbot-*.tar.gz" -mtime +30 -delete
```

Добавьте в crontab:
```bash
0 2 * * * /opt/backup-vodc-chatbot.sh
```

## Устранение неполадок

### Чатбот не отвечает
1. Проверьте статус сервиса: `sudo systemctl status vodc-chatbot`
2. Проверьте логи: `sudo journalctl -u vodc-chatbot -n 50`
3. Проверьте доступность Ollama: `curl http://localhost:11434/api/tags`
4. Проверьте настройки CORS

### Ошибки CORS
Обновите настройки CORS в `widget_server.py`:
```python
CORS(app, origins=["https://your-domain.com"])
```

### Проблемы с RAG-системой
1. Проверьте наличие файла знаний
2. Проверьте доступность Ollama API
3. Проверьте логи RAG-системы

### Проблемы с 1С-Битрикс
1. Проверьте пути к файлам компонента
2. Убедитесь, что PHP-компонент правильно установлен
3. Проверьте настройки сервера в параметрах компонента

## Производительность

### Оптимизация
1. Используйте кэширование ответов
2. Настройте Gunicorn с нужным количеством воркеров
3. Используйте CDN для статических файлов
4. Оптимизируйте размер файла знаний

### Масштабирование
1. Используйте балансировщик нагрузки
2. Разверните несколько экземпляров сервиса
3. Используйте Redis для сессий
4. Настройте мониторинг (Prometheus + Grafana)

## Безопасность

### Проверка безопасности
1. Используйте HTTPS
2. Настройте firewall
3. Ограничьте доступ по IP
4. Используйте аутентификацию при необходимости
5. Регулярно обновляйте зависимости

### Настройка firewall (UFW)
```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## Поддержка

При возникновении проблем:
1. Проверьте этот гайд
2. Просмотрите логи
3. Проверьте GitHub Issues
4. Обратитесь в техническую поддержку ВОККДЦ