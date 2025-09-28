<?php
/**
 * Шаблон компонента чатбота ВОККДЦ
 * Путь: /local/components/vodc/chatbot/templates/.default/template.php
 */

if (!defined("B_PROLOG_INCLUDED") || B_PROLOG_INCLUDED !== true) die();

// Генерируем уникальный ID для виджета
$widgetId = 'vodc-chatbot-' . uniqid();
?>

<!-- Подключение стилей -->
<link rel="stylesheet" href="<?= $this->GetFolder() ?>/styles.css">

<!-- HTML структура чатбота -->
<div id="<?= $widgetId ?>" class="vodc-chatbot-widget vodc-chatbot-<?= strtolower($arParams['WIDGET_POSITION']) ?>">
    
    <!-- Кнопка открытия чата -->
    <div class="chatbot-toggle" onclick="toggleChatbot('<?= $widgetId ?>')">
        <div class="chatbot-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" fill="currentColor"/>
            </svg>
        </div>
        <div class="chatbot-notification" id="<?= $widgetId ?>-notification"></div>
    </div>
    
    <!-- Окно чата -->
    <div class="chatbot-window" id="<?= $widgetId ?>-window">
        <?php if ($arParams['SHOW_HEADER'] === 'Y'): ?>
        <div class="chatbot-header">
            <div class="chatbot-title">
                <img src="<?= $this->GetFolder() ?>/images/vodc-logo.png" alt="ВОККДЦ" class="chatbot-logo">
                <span><?= htmlspecialchars($arParams['HEADER_TEXT']) ?></span>
            </div>
            <div class="chatbot-controls">
                <button onclick="minimizeChatbot('<?= $widgetId ?>')" class="control-btn minimize">−</button>
                <button onclick="closeChatbot('<?= $widgetId ?>')" class="control-btn close">×</button>
            </div>
        </div>
        <?php endif; ?>
        
        <div class="chatbot-messages" id="<?= $widgetId ?>-messages">
            <div class="message bot-message">
                <div class="message-avatar">
                    <img src="<?= $this->GetFolder() ?>/images/bot-avatar.png" alt="Бот">
                </div>
                <div class="message-content">
                    <div class="message-bubble">
                        Здравствуйте! Я интеллектуальный ассистент ВОККДЦ. Чем могу помочь?
                    </div>
                    <div class="message-time"><?= date('H:i') ?></div>
                </div>
            </div>
        </div>
        
        <div class="chatbot-input-area">
            <div class="typing-indicator" id="<?= $widgetId ?>-typing" style="display: none;">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
            <div class="input-container">
                <input type="text" 
                       id="<?= $widgetId ?>-input" 
                       class="chatbot-input" 
                       placeholder="Введите ваш вопрос..."
                       onkeypress="handleKeyPress(event, '<?= $widgetId ?>')"
                       oninput="adjustInputHeight(this)">
                <button onclick="sendMessage('<?= $widgetId ?>')" class="send-button">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" fill="currentColor"/>
                    </svg>
                </button>
            </div>
        </div>
    </div>
</div>

<!-- Подключение скриптов -->
<script>
// Конфигурация чатбота
const VODC_CHATBOT_CONFIG = {
    serverUrl: '<?= $arParams['SERVER_URL'] ?>',
    widgetId: '<?= $widgetId ?>',
    theme: '<?= $arParams['THEME'] ?>',
    sessionId: '<?= session_id() ?>_' + Date.now()
};

// Глобальные функции для управления чатботом
function toggleChatbot(widgetId) {
    const window = document.getElementById(widgetId + '-window');
    const isOpen = window.classList.contains('open');
    
    if (isOpen) {
        window.classList.remove('open');
    } else {
        window.classList.add('open');
        document.getElementById(widgetId + '-input').focus();
        hideNotification(widgetId);
    }
}

function minimizeChatbot(widgetId) {
    const window = document.getElementById(widgetId + '-window');
    window.classList.remove('open');
}

function closeChatbot(widgetId) {
    const widget = document.getElementById(widgetId);
    widget.style.display = 'none';
}

function showNotification(widgetId, count = 1) {
    const notification = document.getElementById(widgetId + '-notification');
    notification.textContent = count;
    notification.style.display = 'block';
}

function hideNotification(widgetId) {
    const notification = document.getElementById(widgetId + '-notification');
    notification.style.display = 'none';
}

function handleKeyPress(event, widgetId) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage(widgetId);
    }
}

function adjustInputHeight(input) {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
}

function showTyping(widgetId) {
    document.getElementById(widgetId + '-typing').style.display = 'flex';
    scrollToBottom(widgetId);
}

function hideTyping(widgetId) {
    document.getElementById(widgetId + '-typing').style.display = 'none';
}

function scrollToBottom(widgetId) {
    const messagesContainer = document.getElementById(widgetId + '-messages');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function addMessage(widgetId, role, content) {
    const messagesContainer = document.getElementById(widgetId + '-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}-message`;
    
    const time = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    
    if (role === 'user') {
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="message-bubble">${content}</div>
                <div class="message-time">${time}</div>
            </div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <img src="<?= $this->GetFolder() ?>/images/bot-avatar.png" alt="Бот">
            </div>
            <div class="message-content">
                <div class="message-bubble">${content}</div>
                <div class="message-time">${time}</div>
            </div>
        `;
    }
    
    messagesContainer.appendChild(messageDiv);
    scrollToBottom(widgetId);
}

async function sendMessage(widgetId) {
    const input = document.getElementById(widgetId + '-input');
    const message = input.value.trim();
    
    if (!message) return;
    
    // Добавляем сообщение пользователя
    addMessage(widgetId, 'user', message);
    input.value = '';
    input.style.height = 'auto';
    
    // Показываем индикатор набора
    showTyping(widgetId);
    
    try {
        const response = await fetch(VODC_CHATBOT_CONFIG.serverUrl + '/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                session_id: VODC_CHATBOT_CONFIG.sessionId
            })
        });
        
        const data = await response.json();
        hideTyping(widgetId);
        
        if (data.response) {
            addMessage(widgetId, 'bot', data.response);
        } else {
            addMessage(widgetId, 'bot', 'Извините, произошла ошибка. Попробуйте еще раз.');
        }
        
    } catch (error) {
        hideTyping(widgetId);
        console.error('Ошибка при отправке сообщения:', error);
        addMessage(widgetId, 'bot', 'Извините, не удалось подключиться к серверу. Попробуйте позже.');
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    // Показываем приветственное уведомление через 3 секунды
    setTimeout(() => {
        if (!document.getElementById(VODC_CHATBOT_CONFIG.widgetId + '-window').classList.contains('open')) {
            showNotification(VODC_CHATBOT_CONFIG.widgetId, 1);
        }
    }, 3000);
});
</script>

<style>
/* Базовые стили для интеграции с Битрикс */
.vodc-chatbot-widget {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    z-index: 1000;
}

/* Адаптация под мобильные устройства */
@media (max-width: 768px) {
    .chatbot-window {
        width: 100vw !important;
        height: 100vh !important;
        max-height: 100vh !important;
        border-radius: 0 !important;
        right: 0 !important;
        bottom: 0 !important;
    }
}
</style>