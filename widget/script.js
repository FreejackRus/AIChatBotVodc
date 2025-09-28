class ChatWidget {
    constructor() {
        this.isMinimized = false;
        this.isTyping = false;
        this.apiEndpoint = 'http://localhost:5000/chat'; // Будет изменено при создании сервера
        this.initializeElements();
        this.bindEvents();
        this.setInitialTime();
    }

    initializeElements() {
        this.chatWidget = document.getElementById('chatWidget');
        this.chatToggle = document.getElementById('chatToggle');
        this.chatHeader = document.querySelector('.chat-header');
        this.chatBody = document.getElementById('chatBody');
        this.chatMessages = document.getElementById('chatMessages');
        this.messageInput = document.getElementById('messageInput');
        this.sendBtn = document.getElementById('sendBtn');
        this.clearBtn = document.getElementById('clearBtn');
        this.restartBtn = document.getElementById('restartBtn');
        this.minimizeBtn = document.getElementById('minimizeBtn');
        this.typingIndicator = document.getElementById('typingIndicator');
    }

    bindEvents() {
        // События для сворачивания/разворачивания
        this.chatToggle.addEventListener('click', () => this.toggleChat());
        this.chatHeader.addEventListener('click', () => this.toggleMinimize());
        this.minimizeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggleMinimize();
        });

        // События для отправки сообщений
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // События для управления чатом
        this.clearBtn.addEventListener('click', () => this.clearChat());
        this.restartBtn.addEventListener('click', () => this.restartChat());

        // Автофокус при открытии
        this.messageInput.addEventListener('focus', () => {
            setTimeout(() => {
                this.messageInput.scrollIntoView({ block: 'nearest' });
            }, 100);
        });
    }

    toggleChat() {
        const isVisible = this.chatWidget.style.display !== 'none';
        
        if (isVisible) {
            this.chatWidget.style.display = 'none';
            this.chatToggle.classList.remove('hidden');
        } else {
            this.chatWidget.style.display = 'flex';
            this.chatToggle.classList.add('hidden');
            this.messageInput.focus();
        }
    }

    toggleMinimize() {
        this.isMinimized = !this.isMinimized;
        
        if (this.isMinimized) {
            this.chatWidget.classList.add('minimized');
            this.chatBody.style.display = 'none';
        } else {
            this.chatWidget.classList.remove('minimized');
            this.chatBody.style.display = 'flex';
            this.messageInput.focus();
        }
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        
        if (!message || this.isTyping) return;

        // Добавляем сообщение пользователя
        this.addMessage(message, 'user');
        this.messageInput.value = '';
        this.messageInput.disabled = true;
        this.sendBtn.disabled = true;

        // Показываем индикатор набора текста
        this.showTypingIndicator();

        try {
            // Отправляем запрос на сервер
            const response = await this.callChatAPI(message);
            
            // Скрываем индикатор набора текста
            this.hideTypingIndicator();
            
            // Добавляем ответ бота
            this.addMessage(response, 'bot');
            
        } catch (error) {
            console.error('Ошибка при отправке сообщения:', error);
            this.hideTypingIndicator();
            
            // Показываем сообщение об ошибке
            this.addMessage(
                'Извините, произошла ошибка при обработке вашего запроса. Попробуйте еще раз позже.',
                'bot',
                true
            );
        }

        this.messageInput.disabled = false;
        this.sendBtn.disabled = false;
        this.messageInput.focus();
    }

    async callChatAPI(message) {
        try {
            const response = await fetch(this.apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    session_id: this.getSessionId()
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            return data.response;
        } catch (error) {
            console.error('Ошибка при обращении к API:', error);
            // В случае ошибки возвращаем тестовый ответ
            return `Я получил ваш вопрос: "${message}". В реальной системе здесь будет ответ от RAG-системы ВОККДЦ.`;
        }
    }

    addMessage(text, sender, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        
        const avatarImg = document.createElement('img');
        avatarImg.src = sender === 'bot' 
            ? "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='white'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z'/%3E%3C/svg%3E"
            : "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='white'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z'/%3E%3C/svg%3E";
        avatar.appendChild(avatarImg);
        
        const content = document.createElement('div');
        content.className = 'message-content';
        
        const textDiv = document.createElement('div');
        textDiv.className = 'message-text';
        textDiv.textContent = text;
        
        if (isError) {
            textDiv.style.background = '#ffebee';
            textDiv.style.color = '#c62828';
        }
        
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = this.getCurrentTime();
        
        content.appendChild(textDiv);
        content.appendChild(timeDiv);
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(content);
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    showTypingIndicator() {
        this.typingIndicator.classList.add('active');
        this.scrollToBottom();
    }

    hideTypingIndicator() {
        this.typingIndicator.classList.remove('active');
    }

    clearChat() {
        this.chatMessages.innerHTML = `
            <div class="message bot-message">
                <div class="message-avatar">
                    <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='white'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z'/%3E%3C/svg%3E" alt="Bot">
                </div>
                <div class="message-content">
                    <div class="message-text">
                        Чат очищен. Чем могу помочь?
                    </div>
                    <div class="message-time">${this.getCurrentTime()}</div>
                </div>
            </div>
        `;
    }

    restartChat() {
        this.clearChat();
        this.addMessage('Здравствуйте! Я чатбот ВОККДЦ. Чем могу помочь?', 'bot');
    }

    scrollToBottom() {
        setTimeout(() => {
            this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
        }, 100);
    }

    getCurrentTime() {
        const now = new Date();
        return now.toLocaleTimeString('ru-RU', { 
            hour: '2-digit', 
            minute: '2-digit' 
        });
    }

    setInitialTime() {
        const initialTime = document.getElementById('initialTime');
        if (initialTime) {
            initialTime.textContent = this.getCurrentTime();
        }
    }

    getSessionId() {
        // Получаем или создаем ID сессии
        let sessionId = sessionStorage.getItem('chatSessionId');
        if (!sessionId) {
            sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            sessionStorage.setItem('chatSessionId', sessionId);
        }
        return sessionId;
    }

    // Метод для обновления API endpoint
    setApiEndpoint(endpoint) {
        this.apiEndpoint = endpoint;
    }
}

// Инициализация виджета при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    const chatWidget = new ChatWidget();
    
    // Делаем виджет доступным глобально для тестирования
    window.chatWidget = chatWidget;
    
    console.log('Виджет чатбота ВОККДЦ инициализирован');
});