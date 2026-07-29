# Подключение к vodc.ru

Рекомендуемый способ — iframe с отдельного origin чат-сервиса:

```html
<iframe
  id="vodc-ai-chat"
  src="https://chat.vodc.ru/?page_url=https%3A%2F%2Fvodc.ru%2F"
  title="Информационный помощник ВОККДЦ"
  style="position:fixed;inset:0;width:100%;height:100%;border:0;z-index:999999"
  loading="lazy"
></iframe>
```

После навигации SPA или открытия другой сущности родительская страница может
без передачи текста обновить контекст:

```js
document.getElementById('vodc-ai-chat').contentWindow.postMessage({
  type: 'vodc:page-context',
  page: {url: location.href, title: document.title}
}, 'https://chat.vodc.ru');
```

Для Яндекс Метрики подпишитесь на анонимные события виджета:

```js
window.addEventListener('message', (event) => {
  if (event.origin !== 'https://chat.vodc.ru') return;
  if (event.data?.type !== 'vodc:chat-event') return;
  ym(YOUR_COUNTER_ID, 'reachGoal', `ai_chat_${event.data.event}`);
});
```

Нельзя передавать в Метрику текст сообщения, URL с query-параметрами, ФИО,
телефон, email или иные данные пациента.
