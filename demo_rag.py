#!/usr/bin/env python3
"""
Демонстрационный скрипт для работы с RAG (Retrieval-Augmented Generation)
Показывает, как обучить чатбота собственной базой знаний
"""

import os
import sys
from colorama import init, Fore, Style
from knowledge_base import KnowledgeBase
from embedding_api import MockEmbeddingAPI
from rag_chatbot import RAGChatBot

def print_header():
    """Вывести заголовок"""
    print(f"{Fore.CYAN}")
    print("=" * 60)
    print("ДЕМОНСТРАЦИЯ RAG (Retrieval-Augmented Generation)")
    print("Локальный чатбот с собственной базой знаний")
    print("=" * 60)
    print(f"{Style.RESET_ALL}")

def demo_knowledge_base():
    """Демонстрация работы с базой знаний"""
    print_header()
    
    print(f"{Fore.YELLOW}1. Создаем базу знаний и добавляем документы...{Style.RESET_ALL}")
    
    # Используем мок-эмбеддинги для демонстрации
    embedding_api = MockEmbeddingAPI()
    kb = KnowledgeBase("demo_knowledge_base")
    
    # Добавляем пример документа
    example_file = "example_knowledge.txt"
    if os.path.exists(example_file):
        print(f"Добавляем документ: {example_file}")
        success = kb.add_document_from_file(example_file, embedding_api)
        if success:
            print(f"{Fore.GREEN}✓ Документ успешно добавлен{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}✗ Ошибка при добавлении документа{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Файл {example_file} не найден{Style.RESET_ALL}")
    
    # Показываем статистику
    stats = kb.get_stats()
    print(f"\n{Fore.BLUE}Статистика базы знаний:{Style.RESET_ALL}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Демонстрируем поиск
    print(f"\n{Fore.YELLOW}2. Тестируем поиск по базе знаний...{Style.RESET_ALL}")
    
    test_queries = [
        "Что такое Python?",
        "Какие есть недостатки у Python?",
        "Как изучать Python?"
    ]
    
    for query in test_queries:
        print(f"\n{Fore.GREEN}Запрос: '{query}'{Style.RESET_ALL}")
        results = kb.search(query, embedding_api, top_k=2)
        
        if results:
            for i, result in enumerate(results):
                doc = result["document"]
                similarity = result["similarity"]
                print(f"  Результат {i+1} (сходство: {similarity:.2f}):")
                print(f"    {doc.content[:100]}...")
        else:
            print(f"  {Fore.YELLOW}Нет результатов{Style.RESET_ALL}")

def demo_rag_chatbot():
    """Демонстрация работы RAG-чатбота"""
    print(f"\n{Fore.YELLOW}3. Запускаем RAG-чатбота...{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Для выхода используйте команду /exit{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Для справки используйте команду /help{Style.RESET_ALL}")
    
    # Создаем чатбота с мок-эмбеддингами
    bot = RAGChatBot(use_mock_embeddings=True)
    
    # Добавляем документ в базу знаний
    if os.path.exists("example_knowledge.txt"):
        bot.add_document_to_kb("example_knowledge.txt")
    
    print(f"\n{Fore.GREEN}Чатбот готов! Задайте вопрос по теме Python:{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Например: 'Расскажи о недостатках Python' или 'Как изучать Python?'{Style.RESET_ALL}")
    
    # Интерактивный режим
    bot.run_interactive()

def create_sample_documents():
    """Создать примерные документы для демонстрации"""
    print(f"{Fore.YELLOW}Создаем примерные документы...{Style.RESET_ALL}")
    
    # Документ о веб-разработке
    web_dev_content = """Веб-разработка на Python

Python - отличный выбор для веб-разработки. Существует множество фреймворков:

1. Django - полнофункциональный фреймворк с батарейками
2. Flask - легковесный и гибкий фреймворк
3. FastAPI - современный фреймворк для API

Преимущества Python в веб-разработке:
- Быстрая разработка прототипов
- Большое сообщество
- Множество готовых библиотек
- Хорошая документация

Пример простого веб-приложения на Flask:
```python
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'
```
"""
    
    # Документ о машинном обучении
    ml_content = """Машинное обучение с Python

Python - стандарт в мире машинного обучения и data science.

Основные библиотеки:
- NumPy - работа с массивами
- Pandas - обработка данных
- Scikit-learn - классические алгоритмы ML
- TensorFlow и PyTorch - глубокое обучение

Процесс создания ML-модели:
1. Сбор и подготовка данных
2. Выбор алгоритма
3. Обучение модели
4. Оценка качества
5. Развертывание модели

Пример простой классификации:
```python
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

# Разделяем данные
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2)

# Создаем и обучаем модель
model = RandomForestClassifier()
model.fit(X_train, y_train)

# Предсказываем
predictions = model.predict(X_test)
```
"""
    
    # Сохраняем документы
    with open("web_development.txt", "w", encoding="utf-8") as f:
        f.write(web_dev_content)
    
    with open("machine_learning.txt", "w", encoding="utf-8") as f:
        f.write(ml_content)
    
    print(f"{Fore.GREEN}✓ Созданы файлы: web_development.txt, machine_learning.txt{Style.RESET_ALL}")

def main():
    """Главная функция демонстрации для ВОККДЦ"""
    init()  # Инициализация colorama
    
    print(f"{Fore.CYAN}=== Демонстрация RAG-системы для ВОККДЦ ==={Style.RESET_ALL}")
    
    # Инициализация RAG-системы
    print("\n1. Инициализация RAG-системы...")
    from rag_system import RAGSystem
    rag = RAGSystem()
    
    # Загрузка комплексной базы знаний ВОККДЦ
    print("\n2. Загрузка базы знаний ВОККДЦ...")
    rag.load_document("knowledge_base/vodc_complete_info.md")
    
    # Примеры поиска по базе знаний ВОККДЦ
    print("\n3. Поиск информации о ВОККДЦ...")
    
    # Пример 1: Информация об отделениях
    query1 = "Какие отделения есть в ВОККДЦ?"
    results1 = rag.search(query1, k=3)
    print(f"\nРезультаты поиска для запроса: '{query1}'")
    for i, result in enumerate(results1, 1):
        print(f"{i}. {result['content'][:300]}...")
        print(f"   Релевантность: {result['score']:.3f}")
        print()
    
    # Пример 2: Информация о ценах
    query2 = "Сколько стоит МРТ в ВОККДЦ?"
    results2 = rag.search(query2, k=2)
    print(f"\nРезультаты поиска для запроса: '{query2}'")
    for i, result in enumerate(results2, 1):
        print(f"{i}. {result['content'][:300]}...")
        print(f"   Релевантность: {result['score']:.3f}")
        print()
    
    # Пример 3: Информация о врачах
    query3 = "Кто главный врач кардиологического отделения?"
    results3 = rag.search(query3, k=2)
    print(f"\nРезультаты поиска для запроса: '{query3}'")
    for i, result in enumerate(results3, 1):
        print(f"{i}. {result['content'][:300]}...")
        print(f"   Релевантность: {result['score']:.3f}")
        print()
    
    # Пример 4: Информация о подготовке к исследованиям
    query4 = "Как подготовиться к сдаче крови?"
    results4 = rag.search(query4, k=2)
    print(f"\nРезультаты поиска для запроса: '{query4}'")
    for i, result in enumerate(results4, 1):
        print(f"{i}. {result['content'][:300]}...")
        print(f"   Релевантность: {result['score']:.3f}")
        print()
    
    # Спрашиваем о запуске чатбота
    print(f"\n{Fore.YELLOW}Хотите запустить интерактивного RAG-чатбота для ВОККДЦ? (y/n): {Style.RESET_ALL}", end="")
    response = input().strip().lower()
    
    if response in ['y', 'yes', 'д', 'да']:
        demo_rag_chatbot()
    else:
        print(f"{Fore.GREEN}Демонстрация завершена!{Style.RESET_ALL}")
        print(f"{Fore.BLUE}Вы можете запустить чатбота позже командой: python rag_chatbot.py{Style.RESET_ALL}")

if __name__ == "__main__":
    main()