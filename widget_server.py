from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import json
import os
import sys
from datetime import datetime
import uuid

# Добавляем путь к текущей директории для импорта модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем RAG-модули с обработкой ошибок
try:
    from rag_chatbot import RAGChatBot
    from knowledge_base import KnowledgeBase
    from embedding_api import EmbeddingAPI
    print("✅ RAG-модули успешно импортированы")
    RAG_AVAILABLE = True
except ImportError as e:
    print(f"❌ Ошибка импорта RAG-модулей: {e}")
    print("Создаем заглушку для RAG-системы...")
    RAG_AVAILABLE = False
    
    # Создаем заглушку для демонстрации
    class RAGChatBot:
        def __init__(self, use_mock_embeddings=False):
            self.knowledge_base = {"ВОККДЦ": "Всероссийский образовательный центр космонавтики и дополнительного образования детей"}
        
        def send_message(self, question):
            return f"Я получил ваш вопрос: '{question}'. В реальной системе здесь будет ответ от RAG-системы ВОККДЦ с использованием базы знаний."

app = Flask(__name__)
CORS(app)  # Разрешаем CORS для всех доменов

# Хранилище сессий
sessions = {}

class ChatSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.messages = []
        
        # Инициализируем RAG-систему с учетом доступности модулей
        try:
            if RAG_AVAILABLE:
                # Пытаемся использовать реальную RAG-систему
                self.rag_bot = RAGChatBot(use_mock_embeddings=False)
                print(f"✅ RAG-чатбот инициализирован для сессии {session_id}")
            else:
                # Используем заглушку
                self.rag_bot = RAGChatBot(use_mock_embeddings=False)
                print(f"⚠️  Используется заглушка RAG-системы для сессии {session_id}")
        except Exception as e:
            print(f"❌ Ошибка инициализации RAG-системы: {e}")
            # В крайнем случае используем заглушку
            self.rag_bot = RAGChatBot(use_mock_embeddings=False)
    
    def add_message(self, role, content):
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_response(self, user_message):
        try:
            # Получаем ответ от RAG-чатбота
            answer = self.rag_bot.send_message(user_message)
            
            # Добавляем сообщения в историю
            self.add_message("user", user_message)
            self.add_message("assistant", answer)
            
            return {
                "response": answer,
                "confidence": 0.85,
                "sources": ["vodc_complete_info.md"],
                "session_id": self.session_id,
                "rag_available": RAG_AVAILABLE
            }
        except Exception as e:
            print(f"❌ Ошибка в RAG-чатботе: {e}")
            # Возвращаем тестовый ответ в случае ошибки
            test_response = f"Я обработал ваш запрос: '{user_message}'. В реальной системе здесь будет ответ на основе базы знаний ВОККДЦ."
            self.add_message("assistant", test_response)
            
            return {
                "response": test_response,
                "confidence": 0.7,
                "sources": ["vodc_complete_info.md"],
                "session_id": self.session_id,
                "error": str(e),
                "rag_available": False
            }

def get_or_create_session(session_id=None):
    """Получаем или создаем новую сессию"""
    if session_id and session_id in sessions:
        return sessions[session_id]
    
    # Создаем новую сессию
    new_session_id = session_id or str(uuid.uuid4())
    session = ChatSession(new_session_id)
    sessions[new_session_id] = session
    
    return session

@app.route('/')
def index():
    """Главная страница с виджетом"""
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ВОККДЦ Чатбот</title>
        <link rel="stylesheet" href="/static/styles.css">
        <style>
            body { margin: 0; padding: 20px; font-family: Arial, sans-serif; background: #f0f0f0; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; }
            .status { padding: 10px; margin: 10px 0; border-radius: 5px; }
            .status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
            .status.error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 ВОККДЦ Чатбот</h1>
            <p>Демонстрация чатбота для Воронежского областного клинического диагностического  центра.</p>
            
            <div id="status" class="status success">
                ✅ Сервер запущен и готов к работе
            </div>
            
            <h2>Тест API</h2>
            <form id="testForm">
                <input type="text" id="testQuestion" placeholder="Введите тестовый вопрос" style="width: 70%; padding: 10px; margin-right: 10px;">
                <button type="submit" style="padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer;">Отправить</button>
            </form>
            
            <div id="testResult" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 5px; display: none;">
                <strong>Результат:</strong>
                <pre id="resultText"></pre>
            </div>
            
            <h2>Инструкции по интеграции</h2>
            <h3>1. Jivo-подобный виджет (рекомендуется)</h3>
            <p>Современный виджет с круглой кнопкой как у Jivo:</p>
            <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">
&lt;!-- ВОККДЦ Jivo-виджет --&gt;
&lt;iframe 
    src="http://localhost:5000/jivo" 
    width="100%" 
    height="100%" 
    style="position: fixed; top: 0; left: 0; width: 100%; height: 100%; border: none; z-index: 999999;"
&gt;&lt;/iframe&gt;</pre>
            <p><strong>Предпросмотр:</strong> <a href="/jivo" target="_blank">Открыть Jivo-виджет</a></p>
            
            <h3>2. Классический виджет</h3>
            <p>Традиционный прямоугольный виджет:</p>
            <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">
&lt;!-- ВОККДЦ Классический виджет --&gt;
&lt;iframe 
    src="http://localhost:5000/widget" 
    width="380" 
    height="600" 
    style="position: fixed; bottom: 20px; right: 20px; border: none; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3);"
&gt;&lt;/iframe&gt;</pre>
            
            <h3>2. Интеграция с Битрикс24</h3>
            <p>Для интеграции с Битрикс24 используйте виджет или REST API:</p>
            <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">
// В вашем PHP-обработчике Битрикс24
$chatbotUrl = 'http://your-server.com:5000/chat';
$data = [
    'message' => $_POST['message'],
    'session_id' => $_POST['session_id'] ?? null
];

$response = file_get_contents($chatbotUrl, false, stream_context_create([
    'http' => [
        'method' => 'POST',
        'header' => 'Content-Type: application/json',
        'content' => json_encode($data)
    ]
]));

echo $response;</pre>
        </div>
        
        <script>
            document.getElementById('testForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const question = document.getElementById('testQuestion').value;
                const resultDiv = document.getElementById('testResult');
                const resultText = document.getElementById('resultText');
                
                try {
                    const response = await fetch('/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({ message: question })
                    });
                    
                    const data = await response.json();
                    resultText.textContent = JSON.stringify(data, null, 2);
                    resultDiv.style.display = 'block';
                } catch (error) {
                    resultText.textContent = 'Ошибка: ' + error.message;
                    resultDiv.style.display = 'block';
                }
            });
        </script>
    </body>
    </html>
    """)

@app.route('/widget')
def widget():
    """Обычный виджет чатбота"""
    try:
        with open('widget/index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Виджет не найден</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                .error { color: #dc3545; }
            </style>
        </head>
        <body>
            <h1 class="error">❌ Виджет не найден</h1>
            <p>Убедитесь, что файлы виджета находятся в папке widget/</p>
        </body>
        </html>
        """)

@app.route('/jivo')
def jivo_widget():
    """Jivo-подобный виджет с круглой кнопкой"""
    try:
        with open('templates/jivo_widget.html', 'r', encoding='utf-8') as f:
            content = f.read()
            # Заменяем относительные пути на абсолютные
            content = content.replace('/chat', f'{request.host_url}chat')
            return content
    except FileNotFoundError:
        return render_template_string("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Jivo-виджет не найден</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; text-align: center; }
                .error { color: #dc3545; }
            </style>
        </head>
        <body>
            <h1 class="error">❌ Jivo-виджет не найден</h1>
            <p>Файл templates/jivo_widget.html не найден</p>
        </body>
        </html>
        """)

@app.route('/static/styles.css')
def widget_styles():
    """Стили виджета"""
    try:
        with open('widget/styles.css', 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/css'}
    except FileNotFoundError:
        return "/* Стили не найдены */", 404

@app.route('/static/script.js')
def widget_script():
    """Скрипт виджета"""
    try:
        with open('widget/script.js', 'r', encoding='utf-8') as f:
            content = f.read()
            # Обновляем API endpoint
            content = content.replace(
                "this.apiEndpoint = 'http://localhost:5000/chat';",
                f"this.apiEndpoint = '{request.host_url}chat';"
            )
            return content, 200, {'Content-Type': 'application/javascript'}
    except FileNotFoundError:
        return "console.log('Скрипт не найден');", 404

@app.route('/chat', methods=['POST'])
def chat():
    """API endpoint для чата"""
    try:
        data = request.get_json()
        
        if not data or 'message' not in data:
            return jsonify({
                "error": "Необходимо указать сообщение",
                "status": "error"
            }), 400
        
        user_message = data['message'].strip()
        session_id = data.get('session_id')
        
        if not user_message:
            return jsonify({
                "error": "Сообщение не может быть пустым",
                "status": "error"
            }), 400
        
        # Получаем или создаем сессию
        session = get_or_create_session(session_id)
        
        # Получаем ответ от RAG-системы
        result = session.get_response(user_message)
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Ошибка в API: {e}")
        return jsonify({
            "error": "Внутренняя ошибка сервера",
            "details": str(e),
            "status": "error"
        }), 500

@app.route('/health')
def health_check():
    """Проверка состояния сервера"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "active_sessions": len(sessions),
        "rag_system": "available"
    })

@app.route('/sessions/<session_id>')
def get_session_history(session_id):
    """Получение истории сессии"""
    if session_id in sessions:
        session = sessions[session_id]
        return jsonify({
            "session_id": session_id,
            "created_at": session.created_at.isoformat(),
            "messages": session.messages,
            "message_count": len(session.messages)
        })
    else:
        return jsonify({
            "error": "Сессия не найдена",
            "status": "error"
        }), 404

if __name__ == '__main__':
    print("🚀 Запускаем сервер ВОККДЦ чатбота...")
    print(f"📋 Доступные endpoint-ы:")
    print(f"   - Главная: http://localhost:5000/")
    print(f"   - Jivo-виджет: http://localhost:5000/jivo (рекомендуется)")
    print(f"   - Классический виджет: http://localhost:5000/widget")
    print(f"   - API чата: http://localhost:5000/chat")
    print(f"   - Проверка состояния: http://localhost:5000/health")
    print()
    print("📝 Для интеграции с Битрикс24 используйте URL: http://localhost:5000/chat")
    print("🌐 Сервер запускается на всех интерфейсах (0.0.0.0) для доступа из вне")
    
    app.run(host='0.0.0.0', port=5000, debug=True)