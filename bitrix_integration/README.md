# Интеграция чатбота ВОККДЦ с 1С-Битрикс

## Установка компонента

### Шаг 1: Копирование файлов
Скопируйте папку `bitrix_integration` в корень вашего сайта на 1С-Битрикс:

```
/local/
  └── components/
      └── vodc/
          └── chatbot/
              ├── component.php
              ├── .description.php
              └── templates/
                  └── .default/
                      ├── template.php
                      ├── styles.css
                      ├── script.js
                      └── images/
                          ├── vodc-logo.png
                          └── bot-avatar.png
```

### Шаг 2: Создание файла .description.php
Создайте файл `/local/components/vodc/chatbot/.description.php`:

```php
<?php
if (!defined("B_PROLOG_INCLUDED") || B_PROLOG_INCLUDED!==true) die();

$arComponentDescription = array(
    "NAME" => "Чатбот ВОККДЦ",
    "DESCRIPTION" => "Интеллектуальный ассистент по вопросам Воронежского областного диагностического  центра",
    "PATH" => array(
        "ID" => "vodc",
        "NAME" => "ВОККДЦ",
    ),
    "ICON" => "/images/icon.gif",
);
?>
```

### Шаг 3: Настройка сервера чатбота
1. Убедитесь, что Flask-сервер запущен на вашем сервере
2. Укажите правильный URL в настройках компонента
3. Настройте CORS в `widget_server.py` для вашего домена

### Шаг 4: Добавление компонента на сайт

#### Через визуальный редактор:
1. Перейдите в режим редактирования страницы
2. Нажмите "Добавить компонент"
3. Найдите "ВОККДЦ" → "Чатбот ВОККДЦ"
4. Перетащите на страницу и настройте параметры

#### Через PHP-код в шаблоне:
```php
<?php
$APPLICATION->IncludeComponent(
    "vodc:chatbot", 
    ".default", 
    array(
        "SERVER_URL" => "https://your-server.com:5000",
        "WIDGET_POSITION" => "bottom-right",
        "THEME" => "vodc",
        "SHOW_HEADER" => "Y",
        "HEADER_TEXT" => "Ассистент ВОККДЦ",
    ),
    false
);
?>
```

## Параметры компонента

| Параметр | Описание | Значения по умолчанию |
|----------|----------|----------------------|
| `SERVER_URL` | URL Flask-сервера | `http://your-server-domain:8085` |
| `WIDGET_POSITION` | Позиция виджета | `bottom-right` |
| `THEME` | Тема оформления | `vodc` |
| `SHOW_HEADER` | Показывать заголовок | `Y` |
| `HEADER_TEXT` | Текст заголовка | `Ассистент ВОККДЦ` |

## Настройка сервера для продакшена

### 1. Установка Gunicorn
```bash
pip install gunicorn
```

### 2. Создание файла конфигурации gunicorn.conf.py:
```python
bind = "0.0.0.0:5000"
workers = 4
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
max_requests = 1000
max_requests_jitter = 50
preload_app = True
```

### 3. Запуск сервера:
```bash
gunicorn widget_server:app -c gunicorn.conf.py
```

### 4. Настройка nginx (опционально):
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Интеграция с системой авторизации Битрикс

### Получение данных текущего пользователя:
```php
<?php
global $USER;
if ($USER->IsAuthorized()) {
    $userId = $USER->GetID();
    $userName = $USER->GetFullName();
    $userEmail = $USER->GetEmail();
    
    // Передаем данные в JavaScript
    ?>
    <script>
    window.VODC_USER_DATA = {
        id: <?= $userId ?>,
        name: '<?= CUtil::JSEscape($userName) ?>',
        email: '<?= CUtil::JSEscape($userEmail) ?>'
    };
    </script>
    <?php
}
?>
```

## Кастомизация внешнего вида

### Переопределение стилей:
Создайте файл `/local/templates/your_template/components/vodc/chatbot/.default/style.css`:

```css
/* Кастомные стили для вашего сайта */
.vodc-chatbot-widget {
    /* Ваши стили */
}

.chatbot-window {
    /* Ваши стили */
}
```

### Добавление собственных команд:
В `script.js` добавьте обработку специфичных для вашего сайта команд:

```javascript
function handleCustomCommand(command) {
    switch(command) {
        case '/help':
            return 'Список доступных команд...';
        case '/contacts':
            return 'Наши контакты: ...';
        default:
            return null;
    }
}
```

## Тестирование

1. Убедитесь, что Flask-сервер запущен и доступен
2. Проверьте консоль браузера на наличие ошибок
3. Протестируйте отправку сообщений
4. Проверьте адаптивность на мобильных устройствах

## Поддержка

При возникновении проблем:
1. Проверьте логи Flask-сервера
2. Убедитесь в правильности CORS-настроек
3. Проверьте доступность сервера из браузера
4. Обратитесь в техническую поддержку ВОККДЦ

## Безопасность

1. Используйте HTTPS для продакшена
2. Настройте CORS только для вашего домена
3. Ограничьте доступ к Flask-серверу по IP
4. Используйте аутентификацию при необходимости