import requests
import json
import time
from typing import Optional, Dict, Any

class LocalChatBot:
    def __init__(self, base_url: str = "http://localhost:1234"):
        self.base_url = base_url
        self.api_url = f"{base_url}/v1/chat/completions"
        self.model = None
        self.conversation_history = []
        
    def check_connection(self) -> bool:
        """Проверка подключения к LM Studio"""
        try:
            response = requests.get(f"{self.base_url}/v1/models")
            if response.status_code == 200:
                models = response.json()
                if models.get('data'):
                    self.model = models['data'][0]['id']
                    print(f"✅ Подключено к LM Studio")
                    print(f"📋 Доступная модель: {self.model}")
                    return True
                else:
                    print("⚠️ Нет доступных моделей")
                    return False
            else:
                print(f"❌ Ошибка подключения: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Не удалось подключиться к LM Studio")
            print("Убедитесь, что LM Studio запущен и сервер активен")
            return False
    
    def send_message(self, message: str, system_prompt: Optional[str] = None) -> str:
        """Отправка сообщения модели"""
        if not self.model:
            if not self.check_connection():
                return "Ошибка: не удалось подключиться к LM Studio"
        
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
                "temperature": 0.7,
                "max_tokens": 2048,
                "stream": False
            }
            
            response = requests.post(
                self.api_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                assistant_message = result['choices'][0]['message']['content']
                
                # Сохранение в историю
                self.conversation_history.append({"role": "user", "content": message})
                self.conversation_history.append({"role": "assistant", "content": assistant_message})
                
                # Ограничение истории (последние 10 сообщений)
                if len(self.conversation_history) > 20:
                    self.conversation_history = self.conversation_history[-20:]
                
                return assistant_message
            else:
                return f"Ошибка: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Ошибка при отправке сообщения: {str(e)}"
    
    def clear_history(self):
        """Очистка истории разговора"""
        self.conversation_history = []
        print("🗑️ История разговора очищена")
    
    def save_conversation(self, filename: str):
        """Сохранение разговора в файл"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.conversation_history, f, ensure_ascii=False, indent=2)
            print(f"💾 Разговор сохранен в {filename}")
        except Exception as e:
            print(f"Ошибка при сохранении: {str(e)}")
    
    def load_conversation(self, filename: str):
        """Загрузка разговора из файла"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                self.conversation_history = json.load(f)
            print(f"📂 Разговор загружен из {filename}")
        except Exception as e:
            print(f"Ошибка при загрузке: {str(e)}")


def main():
    """Интерактивный режим чатбота"""
    print("🤖 Локальный чатбот на базе LM Studio")
    print("=" * 50)
    
    # Системные промпты для разных режимов
    system_prompts = {
        "1": {
            "name": "Ассистент программиста",
            "prompt": "Ты - опытный программист и помощник. Помогай с кодом, объясняй концепции и давай практические советы."
        },
        "2": {
            "name": "Общий ассистент", 
            "prompt": "Ты - полезный ассистент. Отвечай кратко и по существу."
        },
        "3": {
            "name": "Преподаватель",
            "prompt": "Ты - терпеливый преподаватель. Объясняй сложные темы простыми словами и давай примеры."
        }
    }
    
    print("Выберите режим работы:")
    for key, info in system_prompts.items():
        print(f"{key}. {info['name']}")
    
    choice = input("Ваш выбор (1-3): ").strip()
    selected_prompt = system_prompts.get(choice, system_prompts["2"])["prompt"]
    
    chatbot = LocalChatBot()
    
    if not chatbot.check_connection():
        return
    
    print(f"\n🎯 Режим: {system_prompts.get(choice, system_prompts['2'])['name']}")
    print("💡 Команды: /clear - очистить историю, /save - сохранить разговор, /exit - выйти")
    print("=" * 50)
    
    while True:
        try:
            user_input = input("\nВы: ").strip()
            
            if user_input.lower() == '/exit':
                print("👋 До свидания!")
                break
            elif user_input.lower() == '/clear':
                chatbot.clear_history()
                continue
            elif user_input.lower() == '/save':
                filename = f"conversation_{int(time.time())}.json"
                chatbot.save_conversation(filename)
                continue
            elif not user_input:
                continue
            
            print("🤖 Думаю...")
            response = chatbot.send_message(user_input, selected_prompt)
            print(f"Ассистент: {response}")
            
        except KeyboardInterrupt:
            print("\n👋 До свидания!")
            break
        except Exception as e:
            print(f"❌ Ошибка: {str(e)}")


if __name__ == "__main__":
    main()