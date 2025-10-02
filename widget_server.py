from flask import Flask, request, jsonify, render_template_string, send_from_directory
from flask import Response
from flask_cors import CORS
import json
import os
import sys
from datetime import datetime
import uuid
import time
from dotenv import load_dotenv
from ollama_integration import OllamaAPI, OllamaRAGChatBot
from ollama_rag_system import OllamaRAGSystem

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
    print("Используем Ollama-интеграцию...")
    RAG_AVAILABLE = False
    
    # Создаем заглушку для демонстрации
    class RAGChatBot:
        def __init__(self, use_mock_embeddings=False):
            self.knowledge_base = {"ВОККДЦ": "Воронежский областной клинико-диагностический центр"}
        
        def send_message(self, question):
            return f"Я получил ваш вопрос: '{question}'. В реальной системе здесь будет ответ от RAG-системы ВОККДЦ с использованием базы знаний."

# Локальный офлайн-бот для резервного режима (без сетевых запросов)
class LocalFallbackChatBot:
    def __init__(self):
        # Простые ответы по ключевым словам
        self.hotline = "+7 (473) 202-22-22"
        self.address = "г. Воронеж, ул. Студенческая, 10 (пример)"
        self.hours = "Пн–Пт: 8:00–18:00, Сб: 9:00–14:00, Вс: выходной"
    
    def send_message(self, question: str) -> str:
        q = (question or "").lower()
        if any(k in q for k in ["телефон", "горяч", "контакт", "позвон"]):
            return f"Горячая линия ВОККДЦ: {self.hotline}. Чем еще помочь?"
        if any(k in q for k in ["адрес", "как добраться", "где находитс"]):
            return f"Адрес ВОККДЦ: {self.address}. Уточнить расписание можно по телефону {self.hotline}."
        if any(k in q for k in ["режим", "часы", "время работы", "расписание"]):
            return f"Режим работы: {self.hours}. Для записи позвоните: {self.hotline}."
        if any(k in q for k in ["запис", "талон", "приём", "регистратур"]):
            return f"Запись ведется через регистратуру по телефону {self.hotline}. Также возможна запись на месте."
        return (
            "Я работаю в офлайн-режиме без доступа к модели. "
            "Постараюсь помочь: уточните ваш вопрос. При необходимости обратитесь на горячую линию "
            f"ВОККДЦ: {self.hotline}."
        )

app = Flask(__name__)
CORS(app)  # Разрешаем CORS для всех доменов
# Упрощаем JSON-ответы и явно задаём MIME-тип
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
app.config['JSONIFY_MIMETYPE'] = 'application/json'
load_dotenv()  # Загружаем переменные окружения из .env, если файл существует

# Хранилище сессий
sessions = {}
start_time = time.time()

class ChatSession:
    def __init__(self, session_id):
        """Инициализация сессии чата"""
        print(f"🔧 Инициализирую сессию: {session_id}")
        
        self.session_id = session_id
        self.history = []
        # Хранилище сообщений для истории сессии
        self.messages = []
        self.created_at = datetime.now()
        self.ollama_rag = None
        self.rag_bot = None
        
        print(f"📋 Базовые параметры сессии {session_id} установлены")
        
        # Инициализируем AI системы
        try:
            print(f"🤖 Начинаю инициализацию AI систем для сессии {session_id}")
            self._initialize_ai_systems()
            print(f"✅ AI системы для сессии {session_id} инициализированы")
        except Exception as e:
            print(f"❌ Ошибка инициализации AI систем для сессии {session_id}: {e}")
            raise
    
    def _initialize_ai_systems(self):
        """Инициализация AI систем с учетом доступности"""
        try:
            # Пытаемся использовать Ollama
            ollama_url = os.getenv('OLLAMA_URL') or os.getenv('OLLAMA_HOST') or 'http://localhost:11434'
            ollama_model = os.getenv('OLLAMA_MODEL', 'hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:IQ4_XS')
            
            # Создаем OllamaAPI с включенным логированием для отладки
            self.ollama_api = OllamaAPI(base_url=ollama_url, model=ollama_model, verbose=True)  # Включаем логирование для отладки
            
            # Проверяем подключение к Ollama
            if self.ollama_api.check_connection():
                print(f"✅ Ollama подключен для сессии {self.session_id}")
                
                # Инициализируем Ollama RAG систему
                self.ollama_rag = OllamaRAGSystem(self.ollama_api)
                
                # Загружаем базу знаний если доступна
                kb_path = os.getenv('KNOWLEDGE_BASE_PATH', 'knowledge_base')
                if os.path.exists(kb_path):
                    self._load_knowledge_base()
                
            else:
                print(f"⚠️  Ollama недоступен, используем резервную систему")
                self._initialize_fallback_system()
                
        except Exception as e:
            print(f"❌ Ошибка инициализации Ollama: {e}")
            self._initialize_fallback_system()
    
    def _initialize_fallback_system(self):
        """Инициализация резервной системы"""
        try:
            # Всегда используем локальный офлайн-бот, чтобы избежать сетевых ошибок
            self.rag_bot = LocalFallbackChatBot()
            print(f"✅ Используется локальный офлайн-бот для сессии {self.session_id}")
        except Exception as e:
            print(f"❌ Ошибка инициализации резервной системы: {e}")
            self.rag_bot = LocalFallbackChatBot()
    
    def _load_knowledge_base(self):
        """Загрузка базы знаний"""
        try:
            kb_path = os.getenv('KNOWLEDGE_BASE_PATH', 'knowledge_base')
            
            # Проверяем наличие файлов знаний
            knowledge_files = [
                'vodc_complete_info.md',
                'services_info.md',
                'doctors_info.md'
            ]
            
            for filename in knowledge_files:
                filepath = os.path.join(kb_path, filename)
                if os.path.exists(filepath):
                    self.ollama_rag.add_document(filepath)
                    print(f"✅ Загружен файл знаний: {filename}")
            
        except Exception as e:
            print(f"⚠️  Ошибка загрузки базы знаний: {e}")
    
    def add_message(self, role, content):
        # Defensive: ensure messages list exists
        if not hasattr(self, 'messages') or self.messages is None:
            self.messages = []
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_response(self, user_message):
        """Получение ответа от AI системы"""
        print(f"🔄 Обрабатываю запрос: {user_message[:50]}...")
        
        def _strip_greetings(text: str) -> str:
            """Удаляет типовые приветствия и обращения из начала ответа."""
            if not isinstance(text, str):
                return text
            greetings = [
                "Здравствуйте", "Добрый день", "Добрый вечер", "Привет",
                "Здравствуйте!", "Добрый день!", "Добрый вечер!", "Привет!",
                "Здравствуйте,", "Добрый день,", "Добрый вечер,", "Привет,"
            ]
            cleaned = text.strip()
            for g in greetings:
                if cleaned.startswith(g):
                    # Отрезаем приветствие и возможные последующие пробелы/знаки препинания
                    cleaned = cleaned[len(g):].lstrip(" ,—-:;!.")
                    break
            return cleaned.strip()

        try:
            # Пробуем использовать Ollama RAG систему
            if self.ollama_rag:
                print("🤖 Используем Ollama RAG систему")
                result = self.ollama_rag.query(user_message)
                print(f"📊 Результат от RAG системы: {result}")
                
                answer = _strip_greetings(result["response"]) if result.get("response") else ""
                confidence = result["confidence"]
                sources = [source["file"] for source in result["sources"]]
                
                # Добавляем сообщения в историю
                self.add_message("user", user_message)
                self.add_message("assistant", answer)
                
                response_data = {
                    "response": answer,
                    "confidence": confidence,
                    "sources": sources,
                    "session_id": self.session_id,
                    "rag_available": True,
                    "ai_engine": "ollama"
                }
                
                print(f"✅ Возвращаю ответ: {response_data}")
                return response_data
            
            # Используем резервную систему
            elif self.rag_bot:
                answer = _strip_greetings(self.rag_bot.send_message(user_message))
                
                # Добавляем сообщения в историю
                self.add_message("user", user_message)
                self.add_message("assistant", answer)
                
                return {
                    "response": answer,
                    "confidence": 0.85,
                    "sources": ["vodc_complete_info.md"],
                    "session_id": self.session_id,
                    "rag_available": RAG_AVAILABLE,
                    "ai_engine": "legacy"
                }
            
            else:
                # Крайний случай - используем простой ответ
                fallback_response = _strip_greetings("Извините, в данный момент AI система недоступна. Пожалуйста, обратитесь на горячую линию ВОККДЦ: +7 (473) 202-22-22")
                
                self.add_message("user", user_message)
                self.add_message("assistant", fallback_response)
                
                return {
                    "response": fallback_response,
                    "confidence": 0.0,
                    "sources": [],
                    "session_id": self.session_id,
                    "rag_available": False,
                    "ai_engine": "none"
                }
                
        except Exception as e:
            print(f"❌ Ошибка в AI системе: {e}")
            
            # Возвращаем тестовый ответ в случае ошибки
            error_response = _strip_greetings("Извините, произошла ошибка при обработке запроса. Пожалуйста, обратитесь на горячую линию ВОККДЦ: +7 (473) 202-22-22")
            
            self.add_message("assistant", error_response)
            
            return {
                "response": error_response,
                "confidence": 0.0,
                "sources": [],
                "session_id": self.session_id,
                "error": str(e),
                "rag_available": False,
                "ai_engine": "error"
            }

def get_or_create_session(session_id=None):
    """Получаем или создаем новую сессию"""
    print(f"🔍 Ищу сессию с ID: {session_id}")
    
    if session_id and session_id in sessions:
        print(f"✅ Найдена существующая сессия: {session_id}")
        return sessions[session_id]
    
    # Создаем новую сессию
    new_session_id = session_id or str(uuid.uuid4())
    print(f"🆕 Создаю новую сессию с ID: {new_session_id}")
    
    try:
        session = ChatSession(new_session_id)
        sessions[new_session_id] = session
        print(f"✅ Сессия {new_session_id} успешно создана и сохранена")
        return session
    except Exception as e:
        print(f"❌ Ошибка создания сессии: {e}")
        raise

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
    src="http://localhost:8085/jivo" 
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
    src="http://localhost:8085/widget" 
    width="380" 
    height="600" 
    style="position: fixed; bottom: 20px; right: 20px; border: none; border-radius: 16px; box-shadow: 0 20px 60px rgba(0,0,0,0.3);"
&gt;&lt;/iframe&gt;</pre>
            
            <h3>2. Интеграция с Битрикс24</h3>
            <p>Для интеграции с Битрикс24 используйте виджет или REST API:</p>
            <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">
// В вашем PHP-обработчике Битрикс24
$chatbotUrl = 'http://your-server.com:8085/chat';
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
            content = content.replace("this.apiEndpoint = 'http://localhost:8085/chat';", f"this.apiEndpoint = '{request.host_url}chat';")
            content = content.replace("this.apiEndpoint = '/chat';", f"this.apiEndpoint = '{request.host_url}chat';")
            return content, 200, {'Content-Type': 'application/javascript'}
    except FileNotFoundError:
        return "console.log('Скрипт не найден');", 404

@app.route('/static/loader.js')
def widget_loader_script():
    """Загрузчик виджета (инжектор)"""
    try:
        with open('widget/loader.js', 'r', encoding='utf-8') as f:
            content = f.read()
            # Подставляем корректные пути к стилям и основному скрипту
            content = content.replace("/static/styles.css", f"{request.host_url}static/styles.css")
            content = content.replace("/static/script.js", f"{request.host_url}static/script.js")
            return content, 200, {'Content-Type': 'application/javascript'}
    except FileNotFoundError:
        return "console.log('Loader не найден');", 404

# Универсальные заголовки и закрытие соединения для всех ответов
@app.after_request
def add_common_headers(response):
    response.headers['Connection'] = 'close'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# Обработка префлайт-запросов для /chat
@app.route('/chat', methods=['OPTIONS'])
def chat_options():
    return ('', 204)

@app.route('/chat', methods=['POST'])
def chat():
    """API endpoint для чата"""
    print("📨 Получен запрос к /chat endpoint")
    print(f"🔍 Метод запроса: {request.method}")
    print(f"🔍 Content-Type: {request.content_type}")
    print(f"🔍 Headers: {dict(request.headers)}")
    
    try:
        # Более надёжный парсинг JSON: сначала пробуем стандартный способ, затем резервный
        print("🔍 Пытаемся получить JSON данные...")
        data = request.get_json(silent=True)
        print(f"🔍 Полученные данные: {data}")
        if data is None:
            try:
                data = json.loads(request.data.decode('utf-8'))
            except Exception as e:
                print(f"❌ Ошибка парсинга JSON: {e}")
                return jsonify({
                    "error": "Некорректный JSON",
                    "details": str(e),
                    "status": "error"
                }), 400
        
        print(f"📋 Данные запроса: {data}")
        
        if not data or 'message' not in data:
            print("❌ Отсутствует поле message в запросе")
            return jsonify({
                "error": "Необходимо указать сообщение",
                "status": "error"
            }), 400
        
        user_message = data['message'].strip()
        session_id = data.get('session_id')
        
        print(f"💬 Сообщение пользователя: {user_message}")
        print(f"🔑 ID сессии: {session_id}")
        
        if not user_message:
            print("❌ Пустое сообщение")
            return jsonify({
                "error": "Сообщение не может быть пустым",
                "status": "error"
            }), 400
        
        # Получаем или создаем сессию
        print("🔄 Получаю или создаю сессию...")
        session = get_or_create_session(session_id)
        print(f"✅ Сессия получена: {session.session_id}")
        
        # Получаем ответ от RAG-системы
        print("🤖 Получаю ответ от RAG-системы...")
        result = session.get_response(user_message)
        print(f"📤 Отправляю результат: {result}")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Ошибка в API: {e}")
        return jsonify({
            "error": "Внутренняя ошибка сервера",
            "details": str(e),
            "status": "error"
        }), 500

# SSE поток для чата
@app.route('/chat/stream', methods=['GET'])
def chat_stream():
    """SSE endpoint: принимает query параметр message и необязательный session_id."""
    try:
        user_message = request.args.get('message', '').strip()
        session_id = request.args.get('session_id')
        if not user_message:
            return jsonify({"error": "Сообщение не может быть пустым"}), 400

        session = get_or_create_session(session_id)

        def sse_gen():
            # Если доступен RAG, стримим; иначе отдаем единовременно локальный ответ
            if session.ollama_rag:
                for event in session.ollama_rag.stream_query(user_message):
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif session.rag_bot:
                answer = session.rag_bot.send_message(user_message)
                meta = {"type": "meta", "sources": ["offline"], "confidence": 0.85}
                yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({"type": "token", "text": answer}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({"type": "done", "response": answer}, ensure_ascii=False)}\n\n"
            else:
                fallback = "Извините, в данный момент AI система недоступна. Пожалуйста, обратитесь на горячую линию ВОККДЦ: +7 (473) 202-22-22"
                yield f"data: {json.dumps({"type": "done", "response": fallback}, ensure_ascii=False)}\n\n"

        headers = {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
        return Response(sse_gen(), headers=headers)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health_check():
    """Проверка здоровья сервиса"""
    # Проверяем подключение к Ollama
    ollama_status = False
    try:
        ollama_api = OllamaAPI()
        ollama_status = ollama_api.check_connection()
    except:
        ollama_status = False
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "rag_available": RAG_AVAILABLE,
        "ollama_available": ollama_status,
        "active_sessions": len(sessions),
        "uptime": time.time() - start_time if 'start_time' in locals() else 0
    })

@app.route('/ollama/status')
def ollama_status():
    """Проверка статуса Ollama"""
    try:
        ollama_api = OllamaAPI()
        models = ollama_api.get_available_models()
        return jsonify({
            "status": "connected",
            "available_models": models,
            "current_model": os.getenv('OLLAMA_MODEL', 'hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:IQ4_XS')
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

@app.route('/ollama/models')
def list_ollama_models():
    """Список доступных моделей Ollama"""
    try:
        ollama_api = OllamaAPI()
        models = ollama_api.get_available_models()
        return jsonify({"models": models})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    print(f"   - Главная: http://0.0.0.0:8085/")
    print(f"   - Jivo-виджет: http://0.0.0.0:8085/jivo (рекомендуется)")
    print(f"   - Классический виджет: http://0.0.0.0:8085/widget")
    print(f"   - API чата: http://0.0.0.0:8085/chat")
    print(f"   - Проверка состояния: http://0.0.0.0:8085/health")
    print()
    print("📝 Для интеграции с Битрикс24 используйте URL: http://localhost:8085/chat")
    print("🌐 Сервер запускается на всех интерфейсах (0.0.0.0) для доступа из вне")
    
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 8085))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() in ('true', '1', 'yes')
    
    # Отключаем перезагрузчик и включаем потоковый режим для стабильной обработки POST
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
