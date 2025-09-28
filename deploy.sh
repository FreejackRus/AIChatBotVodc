#!/bin/bash

# Скрипт автоматического развертывания чатбота ВОККДЦ
# Использование: ./deploy.sh [environment]
# Где environment: dev, staging, production

set -e  # Остановить выполнение при ошибке

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Параметры по умолчанию
ENVIRONMENT=${1:-dev}
PROJECT_DIR="/opt/vodc-chatbot"
SERVICE_NAME="vodc-chatbot"
USER="vodc"

# Функции для вывода
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Проверка прав root
if [[ $EUID -ne 0 ]]; then
   log_error "Этот скрипт должен быть запущен от root"
   exit 1
fi

log_info "Начинаем развертывание в окружении: $ENVIRONMENT"

# Создание пользователя
if ! id "$USER" &>/dev/null; then
    log_info "Создаем пользователя $USER..."
    useradd -m -s /bin/bash $USER
fi

# Установка зависимостей
log_info "Установка системных зависимостей..."
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl nginx

# Создание директории проекта
log_info "Создание директории проекта..."
mkdir -p $PROJECT_DIR
chown $USER:$USER $PROJECT_DIR

# Клонирование репозитория (если не существует)
if [ ! -d "$PROJECT_DIR/.git" ]; then
    log_info "Клонирование репозитория..."
    sudo -u $USER git clone https://github.com/your-repo/vodc-chatbot.git $PROJECT_DIR
fi

# Переход в директорию проекта
cd $PROJECT_DIR

# Обновление кода
log_info "Обновление кода..."
sudo -u $USER git pull origin main

# Создание виртуального окружения
log_info "Создание виртуального окружения..."
sudo -u $USER python3 -m venv .venv
sudo -u $USER chown -R $USER:$USER .venv

# Установка Python зависимостей
log_info "Установка Python зависимостей..."
sudo -u $USER $PROJECT_DIR/.venv/bin/pip install --upgrade pip
sudo -u $USER $PROJECT_DIR/.venv/bin/pip install -r requirements.txt

# Создание директорий
log_info "Создание необходимых директорий..."
mkdir -p logs
chown $USER:$USER logs

# Настройка окружения
log_info "Настройка окружения..."
if [ ! -f ".env" ]; then
    sudo -u $USER cp .env.example .env
    # Настраиваем окружение в зависимости от типа
    case $ENVIRONMENT in
        production)
            sed -i 's/FLASK_DEBUG=false/FLASK_DEBUG=false/' .env
            sed -i 's/CORS_ORIGINS=\*/CORS_ORIGINS=https:\/\/your-domain.com/' .env
            ;;
        staging)
            sed -i 's/FLASK_DEBUG=false/FLASK_DEBUG=false/' .env
            sed -i 's/CORS_ORIGINS=\*/CORS_ORIGINS=https:\/\/staging.your-domain.com/' .env
            ;;
        dev)
            sed -i 's/FLASK_DEBUG=false/FLASK_DEBUG=true/' .env
            ;;
    esac
fi

# Создание systemd сервиса
log_info "Создание systemd сервиса..."
cat > /etc/systemd/system/$SERVICE_NAME.service << EOF
[Unit]
Description=VODC Chatbot Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/.venv/bin"
ExecStart=$PROJECT_DIR/.venv/bin/gunicorn widget_server:app -c gunicorn.conf.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Настройка nginx
log_info "Настройка nginx..."
cat > /etc/nginx/sites-available/$SERVICE_NAME << EOF
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# Активация nginx конфигурации
ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Запуск сервиса
log_info "Запуск сервиса..."
systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

# Проверка статуса
log_info "Проверка статуса сервиса..."
sleep 5
if systemctl is-active --quiet $SERVICE_NAME; then
    log_info "Сервис успешно запущен!"
else
    log_error "Сервис не запустился. Проверьте логи:"
    journalctl -u $SERVICE_NAME -n 50
    exit 1
fi

# Проверка health endpoint
log_info "Проверка health endpoint..."
sleep 5
if curl -f http://localhost:5000/health > /dev/null 2>&1; then
    log_info "Health check пройден!"
else
    log_error "Health check не пройден. Проверьте настройки."
    exit 1
fi

log_info "Развертывание завершено успешно!"
log_info "Чатбот доступен по адресу: http://localhost:5000"
log_info "Для просмотра логов используйте: journalctl -u $SERVICE_NAME -f"
log_info "Для управления сервисом используйте: systemctl $SERVICE_NAME {start|stop|restart|status}"