import requests
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional
from colorama import init, Fore, Back, Style
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from knowledge_base import KnowledgeBase
from embedding_api import EmbeddingAPI, MockEmbeddingAPI
from system_prompts import SYSTEM_PROMPTS, get_prompt
from synonym_dictionary import expand_synonyms

class RAGChatBot:
    """Чатбот с поддержкой RAG (Retrieval-Augmented Generation)"""
    
    def __init__(self, base_url: str = "http://localhost:11434", use_mock_embeddings: bool = False):
        self.base_url = base_url.rstrip("/")
        self.chat_endpoint = f"{self.base_url}/api/chat"
        self.models_endpoint = f"{self.base_url}/api/tags"
        
        # Инициализация компонентов
        self.console = Console()
        self.knowledge_base = KnowledgeBase("knowledge_base")
        
        # Инициализация API для эмбеддингов
        if use_mock_embeddings:
            self.embedding_api = MockEmbeddingAPI()
        else:
            self.embedding_api = EmbeddingAPI(self.base_url)
        
        # Текущие настройки
        self.current_model = None
        self.current_system_prompt = "general_assistant"
        self.conversation_history = []
        self.use_knowledge_base = True
        self.rag_top_k = 3
        
        # Статистика
        self.stats = {
            "total_messages": 0,
            "total_tokens": 0,
            "total_rag_queries": 0,
            "start_time": datetime.now()
        }
        
        print(f"{Fore.GREEN}🏥 RAG-чатбот для ВОККДЦ инициализирован!{Style.RESET_ALL}")
        print(f"{Fore.BLUE}Я помогу вам найти информацию о Воронежском Областном Клиническом Консультативно-Диагностическом Центре{Style.RESET_ALL}")
        print(f"{Fore.BLUE}База знаний: {self.knowledge_base.get_stats()}{Style.RESET_ALL}")
        
        # Автоматическая загрузка базы знаний ВОККДЦ
        self.load_vodc_knowledge_base()
    
    def get_available_models(self) -> List[str]:
        """Получить списко доступных моделей из Ollama"""
        try:
            response = requests.get(self.models_endpoint, timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models") or data.get("data") or []
                names = []
                for m in models:
                    name = m.get("name") or m.get("id") or m.get("model")
                    if name:
                        names.append(name)
                return names
            else:
                print(f"{Fore.RED}Ошибка при получении списка моделей: {response.status_code}{Style.RESET_ALL}")
                return []
        except Exception as e:
            print(f"{Fore.RED}Ошибка при подключении к Ollama: {e}{Style.RESET_ALL}")
            return []
    
    def get_relevant_context(self, query: str) -> str:
        """Получить релевантный контекст из базы знаний"""
        if not self.use_knowledge_base:
            return ""
        
        try:
            # Расширяем аббревиатуры и синонимы в запросе
            expanded_query = expand_synonyms(query)
            if expanded_query != query:
                print(f"{Fore.CYAN}🔍 Расширен запрос: '{query}' → '{expanded_query}'{Style.RESET_ALL}")
            
            # Ищем похожие документы по расширенному запросу
            results = self.knowledge_base.search(expanded_query, self.embedding_api, self.rag_top_k)
            
            if not results:
                return ""
            
            # Формируем контекст
            context_parts = []
            for i, result in enumerate(results):
                doc = result["document"]
                similarity = result["similarity"]
                
                context_parts.append(f"[Документ {i+1} (релевантность: {similarity:.2f})]: {doc.content}")
            
            self.stats["total_rag_queries"] += 1
            return "\n\n".join(context_parts)
            
        except Exception as e:
            print(f"{Fore.RED}Ошибка при поиске в базе знаний: {e}{Style.RESET_ALL}")
            return ""
    
    def send_message(self, message: str) -> str:
        """Отправить сообщение модели с учетом RAG"""
        if not self.current_model:
            models = self.get_available_models()
            if not models:
                return "Ошибка: Не удалось получить список доступных моделей"
            self.current_model = models[0]
        
        # Получаем контекст из базы знаний
        context = self.get_relevant_context(message)
        
        # Формируем системный промпт с учетом контекста
        system_prompt = get_prompt(self.current_system_prompt)
        
        if context:
            system_prompt += f"\n\nКонтекст из базы знаний:\n{context}\n\nИспользуйте этот контекст для ответа на вопрос пользователя."
        
        # Подготавливаем сообщения
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.conversation_history[-10:])  # Последние 10 сообщений
        messages.append({"role": "user", "content": message})
        
        try:
            payload = {
                "model": self.current_model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 2000,
                    "top_p": 0.9
                }
            }
            
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                assistant_message = (
                    data.get("message", {}).get("content")
                    or (data.get("choices", [{}])[0].get("message", {}).get("content"))
                    or ""
                )
                
                # Обновляем историю
                self.conversation_history.append({"role": "user", "content": message})
                self.conversation_history.append({"role": "assistant", "content": assistant_message})
                
                # Обновляем статистику
                self.stats["total_messages"] += 1
                # У Ollama нет стандартного поля usage, поэтому пропускаем токены
                
                return assistant_message
            else:
                return f"Ошибка: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Ошибка при отправке сообщения: {e}"
    
    def add_document_to_kb(self, file_path: str) -> bool:
        """Добавить документ в базу знаний"""
        if not os.path.exists(file_path):
            print(f"{Fore.RED}Файл не найден: {file_path}{Style.RESET_ALL}")
            return False
        
        print(f"{Fore.YELLOW}Добавляю документ в базу знаний...{Style.RESET_ALL}")
        success = self.knowledge_base.add_document_from_file(file_path, self.embedding_api)
        
        if success:
            print(f"{Fore.GREEN}Документ успешно добавлен в базу знаний{Style.RESET_ALL}")
            print(f"{Fore.BLUE}Обновленная статистика: {self.knowledge_base.get_stats()}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Не удалось добавить документ{Style.RESET_ALL}")
        
        return success
    
    def save_conversation(self, filename: str = None):
        """Сохранить разговор"""
        if not filename:
            filename = f"conversation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        os.makedirs("conversations", exist_ok=True)
        filepath = os.path.join("conversations", filename)
        
        data = {
            "conversation_history": self.conversation_history,
            "stats": self.stats,
            "current_model": self.current_model,
            "current_system_prompt": self.current_system_prompt,
            "saved_at": datetime.now().isoformat()
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"{Fore.GREEN}Разговор сохранен: {filepath}{Style.RESET_ALL}")
    
    def search_vodc_info(self, query: str) -> str:
        """Быстрый поиск информации о ВОККДЦ"""
        try:
            results = self.knowledge_base.search(query, self.embedding_api, top_k=3)
            if not results:
                return "К сожалению, я не нашел информации по вашему запросу в базе данных ВОККДЦ."
            
            response = f"Информация по запросу '{query}':\n\n"
            for i, result in enumerate(results, 1):
                doc = result["document"]
                similarity = result["similarity"]
                response += f"{i}. {doc.content}\n"
                response += f"   (релевантность: {similarity:.3f})\n\n"
            
            return response
        except Exception as e:
            return f"Ошибка при поиске: {str(e)}"

    def load_vodc_knowledge_base(self):
        """Загрузка базы знаний ВОККДЦ"""
        try:
            # Проверяем существование файла с базой знаний ВОККДЦ
            vodc_kb_path = "knowledge_base/vodc_complete_info.md"
            if os.path.exists(vodc_kb_path):
                print(f"{Fore.GREEN}Загрузка базы знаний ВОККДЦ...{Style.RESET_ALL}")
                self.add_document_to_kb(vodc_kb_path)
                print(f"{Fore.GREEN}✅ База знаний ВОККДЦ загружена успешно!{Style.RESET_ALL}")
                self.use_knowledge_base = True
            else:
                print(f"{Fore.YELLOW}⚠️  Файл базы знаний ВОККДЦ не найден: {vodc_kb_path}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Запустите demo_rag.py для создания базы знаний{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}❌ Ошибка загрузки базы знаний ВОККДЦ: {e}{Style.RESET_ALL}")

    def print_help(self):
        """Вывести справку"""
        help_text = """
# 🏥 RAG-чатбот для ВОККДЦ - доступные команды:

## 🔍 Быстрый поиск:
- `/departments` - Информация об отделениях ВОККДЦ
- `/prices` - Информация о ценах на услуги
- `/doctors` - Информация о врачах ВОККДЦ
- `/contacts` - Контактная информация ВОККДЦ
- `/prepare` - Информация о подготовке к исследованиям

## 📋 Базовые команды:
- `/help` - показать эту справку
- `/clear` - очистить историю разговора
- `/save <file>` - сохранить разговор в файл
- `/exit` - выйти

## 📚 Работа с базой знаний:
- `/add <file_path>` - добавить документ в базу знаний
- `/kb_on` - включить использование базы знаний
- `/kb_off` - выключить использование базы знаний
- `/kb_status` - показать статус базы знаний
- `/kb_clear` - очистить базу знаний

## ⚙️ Настройки:
- `/mode <key>` - сменить режим работы (code_assistant, teacher и т.д.)
- `/topk <n>` - установить количество релевантных документов (по умолчанию 3)
- `/models` - показать доступные модели

## 💡 Примеры вопросов:
- Какие отделения есть в ВОККДЦ?
- Сколько стоит МРТ в ВОККДЦ?
- Кто главный врач кардиологического отделения?
- Как подготовиться к сдаче крови?
- Где находится ВОККДЦ?
- Какие анализы можно сдать в ВОККДЦ?
        """
        
        self.console.print(Panel(Markdown(help_text), title="Справка", expand=False))
    
    def run_interactive(self):
        """Запустить интерактивный режим"""
        print(f"{Fore.GREEN}Добро пожаловать в RAG-чатбот!{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Введите /help для списка команд{Style.RESET_ALL}")
        
        while True:
            try:
                # Получаем ввод пользователя
                user_input = input(f"{Fore.BLUE}Вы: {Style.RESET_ALL}").strip()
                
                if not user_input:
                    continue
                
                # Обрабатываем команды
                if user_input.startswith("/"):
                    parts = user_input.split(" ", 1)
                    command = parts[0].lower()
                    arg = parts[1] if len(parts) > 1 else None
                    
                    if command == "/exit":
                        print(f"{Fore.GREEN}До свидания!{Style.RESET_ALL}")
                        break
                    
                    elif command == "/help":
                        self.print_help()
                    
                    elif command == "/clear":
                        self.conversation_history = []
                        print(f"{Fore.GREEN}История очищена{Style.RESET_ALL}")
                    
                    elif command == "/save":
                        self.save_conversation(arg)
                    
                    elif command == "/add":
                        if arg:
                            self.add_document_to_kb(arg)
                        else:
                            print(f"{Fore.RED}Укажите путь к файлу: /add <file_path>{Style.RESET_ALL}")
                    
                    elif command == "/kb_on":
                        self.use_knowledge_base = True
                        print(f"{Fore.GREEN}Использование базы знаний включено{Style.RESET_ALL}")
                    
                    elif command == "/kb_off":
                        self.use_knowledge_base = False
                        print(f"{Fore.YELLOW}Использование базы знаний выключено{Style.RESET_ALL}")
                    
                    elif command == "/kb_stats":
                        stats = self.knowledge_base.get_stats()
                        self.console.print(Panel(str(stats), title="Статистика базы знаний"))
                    
                    elif command == "/kb_list":
                        docs = self.knowledge_base.list_documents()
                        if docs:
                            print(f"{Fore.GREEN}Документы в базе знаний:{Style.RESET_ALL}")
                            for doc in docs:
                                print(f"  - {doc}")
                        else:
                            print(f"{Fore.YELLOW}База знаний пуста{Style.RESET_ALL}")
                    
                    elif command == "/kb_clear":
                        self.knowledge_base.clear()
                        print(f"{Fore.GREEN}База знаний очищена{Style.RESET_ALL}")
                    
                    elif command == "/mode":
                        if arg and arg in SYSTEM_PROMPTS:
                            self.current_system_prompt = arg
                            print(f"{Fore.GREEN}Режим изменен на: {arg}{Style.RESET_ALL}")
                        else:
                            available_modes = ", ".join(SYSTEM_PROMPTS.keys())
                            print(f"{Fore.RED}Доступные режимы: {available_modes}{Style.RESET_ALL}")
                    
                    elif command == "/topk":
                        if arg and arg.isdigit():
                            self.rag_top_k = int(arg)
                            print(f"{Fore.GREEN}Количество релевантных документов: {self.rag_top_k}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.RED}Укажите число: /topk 3{Style.RESET_ALL}")
                    
                    elif command == "/models":
                        models = self.get_available_models()
                        if models:
                            print(f"{Fore.GREEN}Доступные модели:{Style.RESET_ALL}")
                            for model in models:
                                print(f"  - {model}")
                        else:
                            print(f"{Fore.RED}Модели не найдены{Style.RESET_ALL}")
                    
                    elif command == "/departments":
                        print(f"{Fore.YELLOW}Поиск информации об отделениях ВОККДЦ...{Style.RESET_ALL}")
                        response = self.search_vodc_info("отделения ВОККДЦ")
                        self.console.print(Panel(Markdown(response), title="Отделения ВОККДЦ", expand=False))
                    
                    elif command == "/prices":
                        print(f"{Fore.YELLOW}Поиск информации о ценах ВОККДЦ...{Style.RESET_ALL}")
                        response = self.search_vodc_info("цены услуги ВОККДЦ")
                        self.console.print(Panel(Markdown(response), title="Цены на услуги ВОККДЦ", expand=False))
                    
                    elif command == "/doctors":
                        print(f"{Fore.YELLOW}Поиск информации о врачах ВОККДЦ...{Style.RESET_ALL}")
                        response = self.search_vodc_info("врачи специалисты ВОККДЦ")
                        self.console.print(Panel(Markdown(response), title="Врачи ВОККДЦ", expand=False))
                    
                    elif command == "/contacts":
                        print(f"{Fore.YELLOW}Поиск контактной информации ВОККДЦ...{Style.RESET_ALL}")
                        response = self.search_vodc_info("контакты адрес телефон ВОККДЦ")
                        self.console.print(Panel(Markdown(response), title="Контакты ВОККДЦ", expand=False))
                    
                    elif command == "/prepare":
                        print(f"{Fore.YELLOW}Поиск информации о подготовке к исследованиям...{Style.RESET_ALL}")
                        response = self.search_vodc_info("подготовка исследования анализы")
                        self.console.print(Panel(Markdown(response), title="Подготовка к исследованиям", expand=False))
                    
                    else:
                        print(f"{Fore.RED}Неизвестная команда: {command}{Style.RESET_ALL}")
                        print(f"{Fore.YELLOW}Введите /help для списка команд{Style.RESET_ALL}")
                
                else:
                    # Отправляем сообщение модели
                    print(f"{Fore.YELLOW}Обработка...{Style.RESET_ALL}")
                    response = self.send_message(user_input)
                    
                    # Выводим ответ
                    self.console.print(Panel(Markdown(response), title="Ассистент", expand=False))
            
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Используйте /exit для выхода{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Ошибка: {e}{Style.RESET_ALL}")

if __name__ == "__main__":
    # Инициализируем colorama
    init()
    
    # Создаем и запускаем чатбота
    # Используем мок-эмбеддинги для тестирования без Ollama
    bot = RAGChatBot(use_mock_embeddings=False)
    bot.run_interactive()