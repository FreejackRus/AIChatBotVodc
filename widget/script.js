class VodcChatWidget {
    constructor() {
        this.apiBase = new URL('.', window.location.href).origin;
        this.sessionId = sessionStorage.getItem('vodcChatSessionId');
        this.selectedSlotToken = null;
        this.busy = false;
        this.pageContext = this.detectPageContext();
        this.elements = this.getElements();
        this.bindEvents();
        this.scheduleProactiveInvitation();
    }

    getElements() {
        const ids = [
            'chatWidget', 'chatToggle', 'closeChat', 'chatMessages',
            'quickReplies', 'typingIndicator', 'messageForm', 'messageInput',
            'sendButton', 'restartChat', 'connectionStatus',
            'proactiveInvite', 'closeInvite', 'acceptInvite'
        ];
        return Object.fromEntries(ids.map((id) => [id, document.getElementById(id)]));
    }

    detectPageContext() {
        const params = new URLSearchParams(window.location.search);
        const referrer = document.referrer || `${window.location.origin}/`;
        let url;
        try {
            url = new URL(params.get('page_url') || referrer);
        } catch {
            url = new URL(window.location.origin);
        }
        return {
            url: url.toString(),
            title: (params.get('page_title') || document.title).slice(0, 300)
        };
    }

    bindEvents() {
        this.elements.chatToggle.addEventListener('click', () => this.open());
        this.elements.closeChat.addEventListener('click', () => this.close());
        this.elements.acceptInvite.addEventListener('click', () => {
            this.hideInvitation();
            this.open();
        });
        this.elements.closeInvite.addEventListener('click', () => this.hideInvitation());
        this.elements.restartChat.addEventListener('click', () => this.restart());
        this.elements.messageForm.addEventListener('submit', (event) => {
            event.preventDefault();
            this.sendText(this.elements.messageInput.value);
        });
        this.elements.messageInput.addEventListener('keydown', (event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                this.elements.messageForm.requestSubmit();
            }
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && !this.elements.chatWidget.hidden) this.close();
        });
        window.addEventListener('message', (event) => {
            if (!event.data || event.data.type !== 'vodc:page-context') return;
            const candidate = event.data.page || {};
            try {
                const url = new URL(candidate.url);
                if (!['vodc.ru', 'www.vodc.ru', 'localhost', '127.0.0.1'].includes(url.hostname)) return;
                this.pageContext = {
                    url: url.toString(),
                    title: String(candidate.title || '').slice(0, 300)
                };
            } catch {
                return;
            }
        });
    }

    scheduleProactiveInvitation() {
        if (sessionStorage.getItem('vodcInviteShown')) return;
        window.setTimeout(() => {
            if (!this.elements.chatWidget.hidden) return;
            this.elements.proactiveInvite.hidden = false;
            sessionStorage.setItem('vodcInviteShown', '1');
            this.track('proactive_invitation_shown');
        }, 15000);
    }

    hideInvitation() {
        this.elements.proactiveInvite.hidden = true;
    }

    async open() {
        this.hideInvitation();
        this.elements.chatWidget.hidden = false;
        this.elements.chatToggle.hidden = true;
        this.elements.chatToggle.setAttribute('aria-expanded', 'true');
        if (!this.sessionId) await this.createSession();
        this.elements.messageInput.focus();
        this.track('widget_opened');
    }

    close() {
        this.elements.chatWidget.hidden = true;
        this.elements.chatToggle.hidden = false;
        this.elements.chatToggle.setAttribute('aria-expanded', 'false');
        this.elements.chatToggle.focus();
    }

    async createSession() {
        this.setStatus('Подключение…');
        const response = await fetch(`${this.apiBase}/api/v1/sessions`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                page_context: this.pageContext,
                client: {
                    locale: 'ru',
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow',
                    privacy_notice_version: '1.0'
                }
            })
        });
        if (!response.ok) throw new Error(`Session HTTP ${response.status}`);
        const data = await response.json();
        this.sessionId = data.session_id;
        sessionStorage.setItem('vodcChatSessionId', this.sessionId);
        this.elements.chatMessages.replaceChildren();
        this.addMessage(data.welcome, 'assistant');
        this.renderQuickReplies(data.quick_replies);
        this.setStatus('Готов к работе');
    }

    async restart() {
        if (this.busy) return;
        this.sessionId = null;
        this.selectedSlotToken = null;
        sessionStorage.removeItem('vodcChatSessionId');
        try {
            await this.createSession();
        } catch {
            this.addError('Не удалось начать новую сессию. Попробуйте позже.');
        }
    }

    async ensureSession() {
        if (!this.sessionId) await this.createSession();
    }

    async sendText(text) {
        const value = String(text || '').trim();
        if (!value || this.busy) return;
        this.elements.messageInput.value = '';
        this.addMessage(value, 'user');
        await this.streamInput({type: 'text', text: value});
    }

    async sendAction(type, token) {
        if (this.busy) return;
        if (type === 'select_slot') this.selectedSlotToken = token;
        await this.streamInput({type, token});
    }

    async streamInput(input) {
        this.setBusy(true);
        let assistantNode = null;
        try {
            await this.ensureSession();
            const response = await fetch(
                `${this.apiBase}/api/v1/sessions/${this.sessionId}/messages/stream`,
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        input,
                        client_message_id: crypto.randomUUID()
                    })
                }
            );
            if (response.status === 404) {
                await this.createSession();
                throw new Error('Сессия истекла. Повторите сообщение.');
            }
            if (!response.ok || !response.body) throw new Error(`Chat HTTP ${response.status}`);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const {done, value} = await reader.read();
                buffer += decoder.decode(value || new Uint8Array(), {stream: !done});
                const frames = buffer.split('\n\n');
                buffer = frames.pop() || '';
                for (const frame of frames) {
                    const parsed = this.parseSse(frame);
                    if (!parsed) continue;
                    if (parsed.event === 'text_delta') {
                        if (!assistantNode) assistantNode = this.addMessage('', 'assistant');
                        assistantNode.textContent += parsed.data.text || '';
                        this.scrollToBottom();
                    } else if (parsed.event === 'sources') {
                        this.renderSources(parsed.data.items || []);
                    } else if (parsed.event === 'cards') {
                        this.renderCards(parsed.data.items || []);
                    } else if (parsed.event === 'state') {
                        const replies = [...(parsed.data.quick_replies || [])];
                        if (parsed.data.value === 'slot_selected') replies.push('Перейти к записи');
                        this.renderQuickReplies(replies);
                    } else if (parsed.event === 'error') {
                        this.addError(parsed.data.message || 'Временная ошибка');
                    } else if (parsed.event === 'status') {
                        this.setStatus(this.phaseLabel(parsed.data.phase));
                    }
                }
                if (done) break;
            }
        } catch (error) {
            console.error('VODC chat error', error);
            this.addError(error.message || 'Не удалось получить ответ.');
            this.track('widget_error', {code: 'stream_failed'});
        } finally {
            this.setBusy(false);
            this.setStatus('Готов к работе');
        }
    }

    parseSse(frame) {
        let event = 'message';
        const data = [];
        for (const line of frame.split('\n')) {
            if (line.startsWith('event:')) event = line.slice(6).trim();
            if (line.startsWith('data:')) data.push(line.slice(5).trim());
        }
        if (!data.length) return null;
        try {
            return {event, data: JSON.parse(data.join('\n'))};
        } catch {
            return null;
        }
    }

    phaseLabel(phase) {
        return {
            processing: 'Обрабатываю…',
            retrieval: 'Ищу в источниках…',
            generation: 'Формирую ответ…'
        }[phase] || 'Работаю…';
    }

    addMessage(text, role) {
        const article = document.createElement('article');
        article.className = `message message-${role}`;
        const body = document.createElement('div');
        body.className = 'message-text';
        body.textContent = text;
        article.append(body);
        this.elements.chatMessages.append(article);
        this.scrollToBottom();
        return body;
    }

    addError(text) {
        const body = this.addMessage(text, 'error');
        body.setAttribute('role', 'alert');
    }

    renderSources(items) {
        if (!items.length) return;
        const section = document.createElement('section');
        section.className = 'sources';
        const heading = document.createElement('strong');
        heading.textContent = 'Официальные источники';
        section.append(heading);
        const list = document.createElement('ul');
        for (const source of items.slice(0, 3)) {
            const item = document.createElement('li');
            const link = document.createElement('a');
            link.href = source.url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = source.title;
            item.append(link);
            if (source.reviewed_at) {
                const reviewed = document.createElement('small');
                reviewed.textContent = `Проверено: ${source.reviewed_at}`;
                item.append(reviewed);
            }
            list.append(item);
        }
        section.append(list);
        this.elements.chatMessages.append(section);
        this.scrollToBottom();
    }

    renderCards(items) {
        if (!items.length) return;
        const list = document.createElement('div');
        list.className = 'cards';
        for (const card of items) {
            const article = document.createElement('article');
            article.className = `entity-card card-${card.type}`;
            const title = document.createElement('strong');
            title.textContent = card.title;
            article.append(title);
            if (card.subtitle) {
                const subtitle = document.createElement('p');
                subtitle.textContent = card.subtitle;
                article.append(subtitle);
            }
            for (const fact of card.facts || []) {
                const value = document.createElement('small');
                value.textContent = fact;
                article.append(value);
            }
            for (const action of card.actions || []) {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'card-action';
                button.textContent = action.label;
                button.addEventListener('click', () => this.sendAction(action.type, action.token));
                article.append(button);
            }
            list.append(article);
        }
        this.elements.chatMessages.append(list);
        this.scrollToBottom();
    }

    renderQuickReplies(replies) {
        this.elements.quickReplies.replaceChildren();
        for (const reply of replies) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = reply;
            button.addEventListener('click', () => {
                if (reply === 'Перейти к записи') this.openBooking();
                else {
                    this.track('quick_reply_clicked');
                    this.sendText(reply);
                }
            });
            this.elements.quickReplies.append(button);
        }
    }

    async openBooking() {
        if (!this.selectedSlotToken || !this.sessionId) return;
        this.setBusy(true);
        try {
            const response = await fetch(
                `${this.apiBase}/api/v1/sessions/${this.sessionId}/booking-link`,
                {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({slot_token: this.selectedSlotToken})
                }
            );
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail?.message || 'Слот недоступен');
            await this.track('booking_redirect_clicked');
            window.open(data.url, '_blank', 'noopener,noreferrer');
        } catch (error) {
            this.addError(error.message);
        } finally {
            this.setBusy(false);
        }
    }

    async track(type, properties = {}) {
        if (!this.sessionId) return;
        fetch(`${this.apiBase}/api/v1/sessions/${this.sessionId}/events`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({type, properties}),
            keepalive: true
        }).catch(() => {});
        window.parent.postMessage({type: 'vodc:chat-event', event: type, properties}, '*');
    }

    setBusy(value) {
        this.busy = value;
        this.elements.messageInput.disabled = value;
        this.elements.sendButton.disabled = value;
        this.elements.typingIndicator.hidden = !value;
        if (!value) this.elements.messageInput.focus();
    }

    setStatus(text) {
        this.elements.connectionStatus.textContent = text;
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.vodcChatWidget = new VodcChatWidget();
});
