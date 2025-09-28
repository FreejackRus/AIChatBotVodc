# Развертывание чатбота ВОККДЦ на vodc.ru

## Подготовка сервера

### 1. Требования к серверу
- **ОС**: Ubuntu 20.04+ / CentOS 8+ / Debian 11+
- **RAM**: минимум 2GB (рекомендуется 4GB)
- **CPU**: 2 ядра
- **Диск**: 10GB свободного места
- **Порты**: 80, 443, 5000

### 2. Установка Docker и Docker Compose
```bash
# Ubuntu/Debian
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

## Развертывание

### 1. Клонирование репозитория
```bash
cd /opt
git clone https://github.com/your-repo/AIChatBotVodc.git
cd AIChatBotVodc
```

### 2. Настройка окружения
```bash
# Копируем продакшен конфиг
cp .env.production .env

# Редактируем .env файл
nano .env

# Важно изменить:
# - SECRET_KEY - сгенерировать новый
# - CORS_ORIGINS - указать ваши домены
# - LM_STUDIO_URL - если используется
```

### 3. Настройка SSL-сертификатов
```bash
# Создаем директорию для SSL
mkdir -p ssl

# Копируем ваши SSL-сертификаты
cp /path/to/your/certificate.crt ssl/
cp /path/to/your/private.key ssl/
```

### 4. Настройка nginx
Отредактируйте `nginx.conf` для вашего домена:
```nginx
server {
    listen 80;
    server_name vodc.ru www.vodc.ru;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name vodc.ru www.vodc.ru;

    ssl_certificate /etc/nginx/ssl/certificate.crt;
    ssl_certificate_key /etc/nginx/ssl/private.key;

    location / {
        proxy_pass http://vodc-chatbot:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        proxy_pass http://vodc-chatbot:5000/health;
    }
}
```

### 5. Запуск
```bash
# Запускаем в фоновом режиме
docker-compose up -d

# Проверяем статус
docker-compose ps
docker-compose logs -f
```

## Настройка DNS

### 1. Укажите A-записи в вашем DNS:
```
vodc.ru     A   YOUR_SERVER_IP
www.vodc.ru A   YOUR_SERVER_IP
```

### 2. Проверка
```bash
# Проверяем доступность
curl -I https://vodc.ru/health
```

## Интеграция с сайтом vodc.ru

### Вариант 1: Jivo-виджет (рекомендуется)
Добавьте в `<head>` вашего сайта:
```html
<!-- ВОККДЦ Чатбот -->
<script>
(function() {
    var d = document;
    var s = d.createElement('script');
    s.src = 'https://vodc.ru/jivo';
    s.async = true;
    d.head.appendChild(s);
})();
</script>
```

### Вариант 2: iframe
```html
<iframe 
    src="https://vodc.ru/jivo" 
    width="100%" 
    height="100%" 
    style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; border: none; z-index: 999999;"
></iframe>
```

### Вариант 3: API
```javascript
fetch('https://vodc.ru/chat', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({
        message: 'Ваш вопрос здесь',
        session_id: 'уникальный-id-сессии'
    })
})
.then(response => response.json())
.then(data => console.log(data.response));
```

## Мониторинг и логи

### Проверка логов
```bash
# Логи контейнера
docker-compose logs -f vodc-chatbot

# Логи nginx
docker-compose logs -f nginx
```

### Мониторинг состояния
```bash
# Проверка health endpoint
curl https://vodc.ru/health

# Статистика
docker stats
```

## Обновление

### Обновление кода
```bash
cd /opt/AIChatBotVodc
git pull origin main
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Обновление базы знаний
```bash
# Обновите файлы в knowledge_base/
docker-compose restart vodc-chatbot
```

## Безопасность

### 1. Firewall
```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 2. fail2ban
```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

### 3. Регулярные обновления
```bash
sudo apt update && sudo apt upgrade -y
```

## Поддержка

Если возникли проблемы:
1. Проверьте логи: `docker-compose logs -f`
2. Убедитесь, что порты открыты: `sudo netstat -tulpn`
3. Проверьте SSL-сертификаты
4. Проверьте DNS-записи

**Готово!** Теперь ваш чатбот работает на https://vodc.ru