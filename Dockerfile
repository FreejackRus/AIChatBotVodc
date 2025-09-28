# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . .

# Создаем директории для логов
RUN mkdir -p logs

# Создаем непривилегированного пользователя
RUN useradd -m -u 1000 chatbot && chown -R chatbot:chatbot /app
USER chatbot

# Открываем порт
EXPOSE 5000

# Определяем переменные окружения по умолчанию
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=5000
ENV PYTHONPATH=/app

# Запускаем приложение
CMD ["gunicorn", "widget_server:app", "-c", "gunicorn.conf.py"]