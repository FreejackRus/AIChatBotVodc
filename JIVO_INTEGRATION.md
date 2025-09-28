# Интеграция Jivo-подобного виджета ВОККДЦ

## Быстрая интеграция в PHP сайт

### Метод 1: Через iframe (рекомендуется)

Добавьте этот код в ваш PHP файл перед закрывающим тегом `</body>`:

```php
<?php if (!isset($_GET['no_chat'])): ?>
<!-- ВОККДЦ Jivo-виджет -->
<iframe 
    src="http://ВАШ_СЕРВЕР:5000/jivo" 
    width="100%" 
    height="100%" 
    style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; border: none; z-index: 999999; display: none;"
    id="vodcChatFrame"
>&lt;/iframe&gt;

<script>
// Показываем виджет после загрузки страницы
window.addEventListener('load', function() {
    document.getElementById('vodcChatFrame').style.display = 'block';
});
</script>
<?php endif; ?>
```

### Метод 2: Через JavaScript (более гибко)

Создайте файл `vodc-chat.js`:

```javascript
// ВОККДЦ Чатбот - Jivo стиль
(function() {
    // Конфигурация
    var config = {
        serverUrl: 'http://ВАШ_СЕРВЕР:5000',
        position: 'bottom-right',
        buttonColor: '#667eea',
        autoOpen: false
    };

    // Создаем контейнер для чата
    var chatContainer = document.createElement('div');
    chatContainer.id = 'vodc-chat-container';
    chatContainer.innerHTML = '<iframe src="' + config.serverUrl + '/jivo" style="width:100%;height:100%;border:none;"></iframe>';
    
    // Стили для контейнера
    chatContainer.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;z-index:999999;display:none;';
    
    document.body.appendChild(chatContainer);

    // Функция для показа/скрытия чата
    window.toggleVodcChat = function() {
        chatContainer.style.display = chatContainer.style.display === 'none' ? 'block' : 'none';
    };

    // Автоматически показываем если включено
    if (config.autoOpen) {
        setTimeout(function() {
            chatContainer.style.display = 'block';
        }, 3000);
    }
})();
```

Подключите в вашем PHP файле:

```php
<!-- Подключение чатбота ВОККДЦ -->
<script src="/path/to/vodc-chat.js"></script>

<!-- Кнопка вызова чата (по желанию) -->
<button onclick="toggleVodcChat()" style="position: fixed; bottom: 20px; right: 20px; z-index: 999998;">
    💬 Чат с нами
</button>
```

### Метод 3: Для 1С-Битрикс

В шаблоне вашего сайта (например, в `header.php` или `footer.php`):

```php
<?php
// Проверяем, не находимся ли мы в админке
if (!defined('ADMIN_SECTION') || ADMIN_SECTION !== true): 
?>
    <!-- ВОККДЦ Jivo-виджет -->
    <div id="vodc-chat-widget"></div>
    
    <script>
    (function() {
        var widgetDiv = document.getElementById('vodc-chat-widget');
        var iframe = document.createElement('iframe');
        iframe.src = 'http://ВАШ_СЕРВЕР:5000/jivo';
        iframe.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; border: none; z-index: 999999; display: none;';
        iframe.id = 'vodc-chat-frame';
        
        widgetDiv.appendChild(iframe);
        
        // Показываем после загрузки
        window.addEventListener('load', function() {
            document.getElementById('vodc-chat-frame').style.display = 'block';
        });
    })();
    </script>
<?php endif; ?>
```

## Настройки безопасности

### CORS настройка

Если ваш сайт на другом домене, добавьте в `.env` файл:

```env
# Разрешенные домены для CORS
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### HTTPS

Для продакшена используйте HTTPS. В `docker-compose.yml` добавьте:

```yaml
environment:
  - FLASK_ENV=production
  - PREFERRED_URL_SCHEME=https
```

## Кастомизация

### Изменение цветов

В `templates/jivo_widget.html` найдите CSS переменные:

```css
.chat-button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
```

### Изменение текста

В `templates/jivo_widget.html` найдите:

```javascript
this.addMessage('Здравствуйте! 👋 Я чатбот Воронежского областного диагностического  центра...');
```

## Тестирование

1. Откройте ваш сайт в браузере
2. Должна появиться круглая кнопка в правом нижнем углу
3. Нажмите на кнопку - откроется чат
4. Введите тестовое сообщение
5. Проверьте консоль браузера на наличие ошибок

## Проблемы и решения

### Виджет не появляется
- Проверьте, работает ли сервер: `curl http://localhost:5000/health`
- Проверьте CORS настройки
- Посмотрите консоль браузера (F12 → Console)

### Ошибки CORS
- Убедитесь, что ваш домен добавлен в CORS_ORIGINS
- Проверьте, что сервер перезапущен после изменений

### Мобильная версия
- Виджет адаптивен и будет работать на мобильных устройствах
- На маленьких экранах откроется на полный экран

## API интеграция

Если нужно более глубокое интегрирование, используйте напрямую API:

```php
<?php
function sendToVodcChat($message, $sessionId = null) {
    $url = 'http://ВАШ_СЕРВЕР:5000/chat';
    
    $data = [
        'message' => $message,
        'session_id' => $sessionId
    ];
    
    $options = [
        'http' => [
            'header'  => "Content-type: application/json\r\n",
            'method'  => 'POST',
            'content' => json_encode($data)
        ]
    ];
    
    $context  = stream_context_create($options);
    $result = file_get_contents($url, false, $context);
    
    return json_decode($result, true);
}

// Использование
$response = sendToVodcChat('Привет, расскажи о центре');
echo $response['response'];
?>
```

Готово! 🎉 Ваш Jivo-подобный виджет теперь должен работать на сайте.