import requests
import json
import time
import os
from typing import Optional, Dict, Any, List
from datetime import datetime
from system_prompts import SYSTEM_PROMPTS, get_prompt, list_available_prompts, get_prompt_name

class AdvancedLocalChatBot:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/chat"
        self.models_endpoint = f"{self.base_url}/api/tags"
        # Выбор модели: из переменной окружения или дефолт Qwen3-30B
        self.model = os.getenv('OLLAMA_MODEL') or "hf.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF:IQ4_XS"
        self.conversation_history = []
        self.current_prompt_key = "general_assistant"
        self.current_prompt = get_prompt(self.current_prompt_key)
        self.conversations_dir = "conversations"
        
        # Создание директории для сохранения разговоров
        if not os.path.exists(self.conversations_dir):
            os.makedirs(self.conversations_dir)
    
    def check_connection(self) -> bool:
        """Проверка подключения к Ollama"""
        try:
            response = requests.get(self.models_endpoint, timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models") or data.get("data") or []
                if models:
                    first = models[0]
                    self.model = first.get("name") or first.get("id") or first.get("model")
                    print(f"✅ Подключено к Ollama")
                    print(f"📋 Доступная модель: {self.model}")
                    return True
                else:
                    print("⚠️ Нет доступных моделей")
                    return False
            else:
                print(f"❌ Ошибка подключения: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Не удалось подключиться к Ollama")
            print("Убедитесь, что Ollama запущен и сервер активен")
            return False
        except requests.exceptions.Timeout:
            print("❌ Превышено время ожидания подключения")
            return False
        except Exception as e:
            print(f"❌ Неожиданная ошибка: {str(e)}")
            return False
    
    def set_system_prompt(self, prompt_key: str):
        """Установка системного промпта"""
        if prompt_key in SYSTEM_PROMPTS:
            self.current_prompt_key = prompt_key
            self.current_prompt = get_prompt(prompt_key)
            print(f"🎯 Режим изменен на: {get_prompt_name(prompt_key)}")
        else:
            print(f"❌ Неизвестный промпт: {prompt_key}")
            print("Доступные промпты:", ", ".join(SYSTEM_PROMPTS.keys()))
    
    def send_message(self, message: str, use_system_prompt: bool = True) -> str:
        """Отправка сообщения модели"""
        if not self.model:
            if not self.check_connection():
                return "Ошибка: не удалось подключиться к Ollama"
        
        # Формирование контекста с историей разговора
        messages = []
        
        if use_system_prompt and self.current_prompt:
            messages.append({"role": "system", "content": self.current_prompt})
        
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
                    "temperature": 0.7,
                    "num_predict": 2048,
                    "top_p": 0.9,
                    "frequency_penalty": 0.0,
                    "presence_penalty": 0.0
                }
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                assistant_message = (
                    result.get("message", {}).get("content")
                    or (result.get("choices", [{}])[0].get("message", {}).get("content"))
                    or ""
                )
                
                # Сохранение в историю
                self.conversation_history.append({"role": "user", "content": message})
                self.conversation_history.append({"role": "assistant", "content": assistant_message})
                
                # Ограничение истории (последние 20 сообщений)
                if len(self.conversation_history) > 40:
                    self.conversation_history = self.conversation_history[-40:]
                
                return assistant_message
            else:
                return f"Ошибка: {response.status_code} - {response.text}"
                
        except requests.exceptions.Timeout:
            return "Ошибка: превышено время ожидания ответа"
        except Exception as e:
            return f"Ошибка при отправке сообщения: {str(e)}"
    
    def clear_history(self):
        """Очистка истории разговора"""
        self.conversation_history = []
        print("🗑️ История разговора очищена")
    
    def save_conversation(self, filename: str = None):
        """Сохранение разговора в файл"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.conversations_dir}/conversation_{timestamp}.json"
        
        try:
            conversation_data = {
                "timestamp": datetime.now().isoformat(),
                "model": self.model,
                "system_prompt": {
                    "key": self.current_prompt_key,
                    "name": get_prompt_name(self.current_prompt_key),
                    "content": self.current_prompt
                },
                "history": self.conversation_history
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(conversation_data, f, ensure_ascii=False, indent=2)
            print(f"💾 Разговор сохранен в {filename}")
            return filename
        except Exception as e:
            print(f"Ошибка при сохранении: {str(e)}")
            return None
    
    def load_conversation(self, filename: str):
        """Загрузка разговора из файла"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                conversation_data = json.load(f)
            
            self.conversation_history = conversation_data.get("history", [])
            if "system_prompt" in conversation_data:
                prompt_key = conversation_data["system_prompt"].get("key", "general_assistant")
                self.set_system_prompt(prompt_key)
            
            print(f"📂 Разговор загружен из {filename}")
            print(f"📋 Загружено {len(self.conversation_history)} сообщений")
            return True
        except Exception as e:
            print(f"❌ Ошибка при загрузке: {str(e)}")
            return False
    
    def list_saved_conversations(self):
        """Список сохраненных разговоров"""
        try:
            files = [f for f in os.listdir(self.conversations_dir) if f.endswith('.json')]
            if not files:
                print("📋 Нет сохраненных разговоров")
                return []
            
            print("📋 Сохраненные разговоры:")
            for i, file in enumerate(files, 1):
                filepath = os.path.join(self.conversations_dir, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    timestamp = data.get("timestamp", "Неизвестно")
                    prompt_name = data.get("system_prompt", {}).get("name", "Неизвестно")
                    message_count = len(data.get("history", []))
                    print(f"{i}. {file}")
                    print(f"   Время: {timestamp}")
                    print(f"   Режим: {prompt_name}")
                    print(f"   Сообщений: {message_count}")
                    print()
                except:
                    print(f"{i}. {file} (ошибка чтения)")
            
            return files
        except Exception as e:
            print(f"❌ Ошибка при получении списка: {str(e)}")
            return []
    
    def show_conversation_stats(self):
        """Показать статистику текущего разговора"""
        print(f"📊 Статистика разговора:")
        print(f"   Текущий режим: {get_prompt_name(self.current_prompt_key)}")
        print(f"   История: {len(self.conversation_history)} сообщений")
        print(f"   Модель: {self.model or 'Не подключена'}")
        
        if self.conversation_history:
            user_messages = len([m for m in self.conversation_history if m["role"] == "user"])
            assistant_messages = len([m for m in self.conversation_history if m["role"] == "assistant"])
            print(f"   Пользователь: {user_messages} сообщений")
            print(f"   Ассистент: {assistant_messages} сообщений")


def main():
    """Расширенный интерактивный режим чатбота"""
    print("🤖 Расширенный локальный чатбот на базе Ollama")
    print("=" * 60)
    
    chatbot = AdvancedLocalChatBot()
    
    if not chatbot.check_connection():
        return
    
    print("\n🎯 Доступные режимы:")
    prompts = list_available_prompts()
    for key, name in prompts.items():
        print(f"   {key}: {name}")
    
    print(f"\n💡 Текущий режим: {get_prompt_name(chatbot.current_prompt_key)}")
    print("\n📋 Команды:")
    print("   /mode <ключ> - сменить режим работы")
    print("   /clear - очистить историю")
    print("   /save [имя_файла] - сохранить разговор")
    print("   /load <имя_файла> - загрузить разговор")
    print("   /list - список сохраненных разговоров")
    print("   /stats - показать статистику")
    print("   /help - показать справку")
    print("   /exit - выйти")
    print("=" * 60)
    
    while True:
        try:
            user_input = input("\nВы: ").strip()
            
            if not user_input:
                continue
            
            # Обработка команд
            if user_input.startswith('/'):
                parts = user_input.split(' ', 1)
                command = parts[0].lower()
                
                if command == '/exit':
                    print("👋 До свидания!")
                    break
                elif command == '/clear':
                    chatbot.clear_history()
                    continue
                elif command == '/save':
                    filename = parts[1] if len(parts) > 1 else None
                    chatbot.save_conversation(filename)
                    continue
                elif command == '/load':
                    if len(parts) > 1:
                        filename = parts[1]
                        if not filename.endswith('.json'):
                            filename += '.json'
                        if not filename.startswith(chatbot.conversations_dir):
                            filename = os.path.join(chatbot.conversations_dir, filename)
                        chatbot.load_conversation(filename)
                    else:
                        print("❌ Укажите имя файла: /load <имя_файла>")
                    continue
                elif command == '/list':
                    chatbot.list_saved_conversations()
                    continue
                elif command == '/stats':
                    chatbot.show_conversation_stats()
                    continue
                elif command == '/mode':
                    if len(parts) > 1:
                        new_mode = parts[1].strip()
                        chatbot.set_system_prompt(new_mode)
                    else:
                        print("❌ Укажите режим: /mode <ключ>")
                        print("Доступные режимы:", ", ".join(prompts.keys()))
                    continue
                elif command == '/help':
                    print("📋 Справка по командам:")
                    print("   /mode <ключ> - сменить режим работы")
                    print("   /clear - очистить историю")
                    print("   /save [имя_файла] - сохранить разговор")
                    print("   /load <имя_файла> - загрузить разговор")
                    print("   /list - список сохраненных разговоров")
                    print("   /stats - показать статистику")
                    print("   /help - показать справку")
                    print("   /exit - выйти")
                    continue
                else:
                    print(f"❌ Неизвестная команда: {command}")
                    print("Используйте /help для списка команд")
                    continue
            
            print("🤖 Думаю...")
            response = chatbot.send_message(user_input)
            print(f"Ассистент: {response}")
            
        except KeyboardInterrupt:
            print("\n👋 До свидания!")
            break
        except Exception as e:
            print(f"❌ Ошибка: {str(e)}")


if __name__ == "__main__":
    main()