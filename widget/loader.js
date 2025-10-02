// Simple loader to inject VODC chat widget without iframe
(function() {
  var serverUrl = (function() {
    // Try to infer server from current script src
    try {
      var currentScript = document.currentScript || (function() {
        var scripts = document.getElementsByTagName('script');
        return scripts[scripts.length - 1];
      })();
      var src = currentScript && currentScript.src ? currentScript.src : '';
      // e.g., https://example.com:8085/static/loader.js -> https://example.com:8085/
      var m = src.match(/^(https?:\/\/[^\s]+?)\/?static\/loader\.js/);
      if (m) return m[1] + '/';
    } catch (e) {}
    return (window.location.origin + '/');
  })();

  function addCss(href) {
    var link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
  }

  function addScript(src, onload) {
    var s = document.createElement('script');
    s.type = 'text/javascript';
    s.async = true;
    s.src = src;
    if (onload) s.onload = onload;
    document.body.appendChild(s);
  }

  function createWidgetMarkup() {
    var container = document.createElement('div');
    container.innerHTML = "\n    <div class=\"chat-widget\" id=\"chatWidget\">\n        <div class=\"chat-header\">\n            <div class=\"chat-title\">\n                <img src=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'%3E%3C/path%3E%3C/svg%3E\" alt=\"Chat\" class=\"chat-icon\">\n                <span>ВОККДЦ Помощник</span>\n            </div>\n            <button class=\"minimize-btn\" id=\"minimizeBtn\">\n                <svg width=\"16\" height=\"16\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"white\" stroke-width=\"2\">\n                    <line x1=\"5\" y1=\"12\" x2=\"19\" y2=\"12\"></line>\n                </svg>\n            </button>\n        </div>\n        \n        <div class=\"chat-body\" id=\"chatBody\">\n            <div class=\"chat-messages\" id=\"chatMessages\">\n                <div class=\"message bot-message\">\n                    <div class=\"message-avatar\">\n                        <img src=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='white'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z'/%3E%3C/svg%3E\" alt=\"Bot\">\n                    </div>\n                    <div class=\"message-content\">\n                        <div class=\"message-text\">\n                            Здравствуйте! Я чатбот ВОККДЦ. Чем могу помочь?\n                        </div>\n                        <div class=\"message-time\" id=\"initialTime\"></div>\n                    </div>\n                </div>\n            </div>\n            \n            <div class=\"typing-indicator\" id=\"typingIndicator\">\n                <div class=\"typing-dot\"></div>\n                <div class=\"typing-dot\"></div>\n                <div class=\"typing-dot\"></div>\n            </div>\n        </div>\n        \n        <div class=\"chat-footer\">\n            <div class=\"input-container\">\n                <input type=\"text\" id=\"messageInput\" placeholder=\"Введите ваш вопрос...\" maxlength=\"500\">\n                <button id=\"sendBtn\" class=\"send-btn\">\n                    <svg width=\"20\" height=\"20\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\">\n                        <line x1=\"22\" y1=\"2\" x2=\"11\" y2=\"13\"></line>\n                        <polygon points=\"22 2 15 22 11 13 2 9 22 2\"></polygon>\n                    </svg>\n                </button>\n            </div>\n            <div class=\"chat-controls\">\n                <button id=\"clearBtn\" class=\"control-btn\">Очистить</button>\n                <button id=\"restartBtn\" class=\"control-btn\">Начать заново</button>\n            </div>\n        </div>\n    </div>\n\n    <div class=\"chat-toggle\" id=\"chatToggle\">\n        <img src=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'%3E%3C/path%3E%3C/svg%3E\" alt=\"Chat\">\n    </div>\n    ";
    // return as node list to attach to body
    var frag = document.createDocumentFragment();
    while (container.firstChild) frag.appendChild(container.firstChild);
    return frag;
  }

  function init() {
    // 1) add CSS
    addCss(serverUrl + 'static/styles.css');
    // 2) inject markup if not present
    if (!document.getElementById('chatWidget')) {
      document.body.appendChild(createWidgetMarkup());
    }
    // 3) add script.js
    addScript(serverUrl + 'static/script.js');
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    init();
  } else {
    window.addEventListener('DOMContentLoaded', init, false);
  }
})();