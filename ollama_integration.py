import requests
import json
from typing import List, Optional, Dict, Any
import time

class OllamaAPI:
    """Интеграция с Ollama API для работы с локальными моделями"""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:3b", verbose: bool = True):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.verbose = verbose
        self.api_chat_url = f"{self.base_url}/api/chat"
        self.api_generate_url = f"{self.base_url}/api/generate"
        self.api_tags_url = f"{self.base_url}/api/tags"
        self.conversation_history = []
        
    def check_connection(self) -> bool:
        """Проверка подключения к Ollama"""
        try:
            response = requests.get(self.api_tags_url, timeout=10)
            if response.status_code == 200:
                models = response.json()
                if 'models' in models and len(models['models']) > 0:
                    available_models = [m['name'] for m in models['models']]
                    if self.verbose:
                        print(f"✅ Подключено к Ollama")
                        print(f"📋 Доступные модели: {available_models}")
                    
                    # Проверяем, доступна ли нужная модель
                    if self.model not in available_models:
                        if self.verbose:
                            print(f"⚠️ Модель {self.model} не найдена, используем первую доступную")
                        self.model = available_models[0]
                    
                    return True
                else:
                    if self.verbose:
                        print("⚠️ Нет доступных моделей")
                    return False
            else:
                if self.verbose:
                    print(f"❌ Ошибка подключения: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            if self.verbose:
                print("❌ Не удалось подключиться к Ollama")
                print("Убедитесь, что Ollama запущен: systemctl start ollama")
            return False
        except requests.exceptions.Timeout:
            if self.verbose:
                print("❌ Превышено время ожидания подключения")
            return False
        except Exception as e:
            if self.verbose:
                print(f"❌ Неожиданная ошибка: {str(e)}")
            return False
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей"""
        try:
            response = requests.get(self.api_tags_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return [model['name'] for model in data.get('models', [])]
            else:
                print(f"Ошибка при получении списка моделей: {response.status_code}")
                return []
        except Exception as e:
            print(f"Ошибка при получении моделей: {e}")
            return []
    
    def send_message(self, message: str, system_prompt: Optional[str] = None, 
                    temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """Отправка сообщения модели через чат API"""
        if not self.check_connection():
            return "Ошибка: не удалось подключиться к Ollama"
        
        # Формирование контекста с историей разговора
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Добавление истории разговора
        messages.extend(self.conversation_history)
        
        # Добавление нового сообщения пользователя
        messages.append({"role": "user", "content": message})
        
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "top_p": 0.9,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0
                }
            }
            
            response = requests.post(
                self.api_chat_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                assistant_message = result['message']['content']
                
                # Обновление истории разговора
                self.conversation_history.append({"role": "user", "content": message})
                self.conversation_history.append({"role": "assistant", "content": assistant_message})
                
                # Ограничение истории (последние 10 сообщений)
                if len(self.conversation_history) > 20:
                    self.conversation_history = self.conversation_history[-20:]
                
                return assistant_message
            else:
                return f"Ошибка: {response.status_code} - {response.text}"
                
        except requests.exceptions.Timeout:
            return "Ошибка: превышено время ожидания ответа"
        except Exception as e:
            return f"Ошибка при отправке сообщения: {str(e)}"
    
    def generate_text(self, prompt: str, system_prompt: Optional[str] = None,
                     temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """Генерация текста через generate API (без контекста)"""
        if not self.check_connection():
            return "Ошибка: не удалось подключиться к Ollama"
        
        # Формирование полного промпта
        full_prompt = ""
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"
        else:
            full_prompt = prompt
        
        if self.verbose:
            print(f"🤖 Отправляю запрос к Ollama модели {self.model}...")
        
        try:
            payload = {
                "model": self.model,
                "prompt": full_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                    "top_p": 0.9,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0
                }
            }
            
            if self.verbose:
                print(f"📤 Отправляю POST запрос к {self.api_generate_url}")
            
            response = requests.post(
                self.api_generate_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30  # Увеличен таймаут до 30 секунд для стабильности
            )
            
            if self.verbose:
                print(f"📥 Получен ответ со статусом: {response.status_code}")
            
            if response.status_code == 200:
                if self.verbose:
                    print(f"🔍 Начинаю парсинг JSON ответа...")
                try:
                    result = response.json()
                    if self.verbose:
                        print(f"✅ JSON успешно распарсен")
                        print(f"🔍 Ключи в ответе: {list(result.keys())}")
                        response_text = result.get('response', '')
                        print(f"✅ Ответ получен успешно (длина: {len(response_text)} символов)")
                    return result['response']
                except json.JSONDecodeError as e:
                    error_msg = f"Ошибка парсинга JSON: {str(e)}"
                    if self.verbose:
                        print(f"❌ {error_msg}")
                        print(f"🔍 Сырой ответ: {response.text[:500]}...")
                    return error_msg
            else:
                error_msg = f"Ошибка: {response.status_code} - {response.text}"
                if self.verbose:
                    print(f"❌ {error_msg}")
                return error_msg
                
        except requests.exceptions.Timeout:
            error_msg = "Ошибка: превышено время ожидания ответа (30 сек)"
            if self.verbose:
                print(f"⏰ {error_msg}")
            return error_msg
        except requests.exceptions.ConnectionError:
            error_msg = "Ошибка: потеряно соединение с Ollama"
            if self.verbose:
                print(f"🔌 {error_msg}")
            return error_msg
        except Exception as e:
            error_msg = f"Ошибка при генерации: {str(e)}"
            if self.verbose:
                print(f"💥 {error_msg}")
            return error_msg
    
    def clear_history(self):
        """Очистка истории разговора"""
        self.conversation_history = []
    
    def set_model(self, model: str):
        """Смена модели"""
        self.model = model
        print(f"Модель изменена на: {model}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """Получение информации о текущей модели"""
        try:
            response = requests.get(self.api_tags_url, timeout=10)
            if response.status_code == 200:
                models = response.json().get('models', [])
                for model_info in models:
                    if model_info['name'] == self.model:
                        return model_info
                return {}
            else:
                return {}
        except Exception as e:
            print(f"Ошибка при получении информации о модели: {e}")
            return {}


class OllamaRAGChatBot:
    """RAG чатбот с использованием Ollama"""
    
    def __init__(self, ollama_api: OllamaAPI, knowledge_base_path: str = "knowledge_base"):
        self.ollama = ollama_api
        self.knowledge_base_path = knowledge_base_path
        self.system_prompt = """Ты - помощник Воронежского областного клинико-диагностического центра (ВОККДЦ).
        Ты отвечаешь на вопросы пациентов и сотрудников, используя предоставленную информацию.
        Будь вежливым, профессиональным и информативным.
        Не добавляй приветствия, обращения к пользователю или подписи; сразу отвечай по сути.
        Если ты не знаешь ответа, честно скажи об этом и предложи обратиться на горячую линию.
        """
    
    def process_query(self, query: str, context_documents: List[str] = None) -> str:
        """Обработка запроса с контекстом"""
        if context_documents:
            # Формируем контекст из документов
            context = "\n\n".join(context_documents)
            enhanced_prompt = f"""Используя следующую информацию из базы знаний ВОККДЦ:

{context}

Ответь на вопрос: {query}

Если в предоставленной информации нет ответа, скажи честно об этом."""
            
            return self.ollama.send_message(enhanced_prompt, self.system_prompt)
        else:
            # Без контекста - просто отвечаем на вопрос
            return self.ollama.send_message(query, self.system_prompt)