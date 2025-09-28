#!/usr/bin/env python3
"""
Тестирование распознавания аббревиатур ВОККДЦ в RAG-системе с учетом словаря синонимов
"""

import os
import sys
from datetime import datetime
from synonym_dictionary import expand_synonyms
from rag_chatbot import RAGChatBot

def test_abbreviations():
    """Тестирование различных вариантов аббревиатур"""
    
    print("🧪 Тестирование распознавания аббревиатур ВОККДЦ")
    print("=" * 60)
    
    # Тестирование словаря синонимов
    print("📚 Тестирование словаря синонимов:")
    test_queries = ["ВОККДЦ", "воккдц?", "что такое воккдц", "VOKKDC"]
    for query in test_queries:
        expanded = expand_synonyms(query)
        print(f"  '{query}' → '{expanded}'")
    print()
    
    # Инициализируем RAG-чатбота
    try:
        bot = RAGChatBot(use_mock_embeddings=False)
        print("✅ RAG-чатбот успешно инициализирован")
        print(f"📚 База знаний: {bot.knowledge_base.get_stats()}")
        print()
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        return
    
    # Список тестовых вопросов
    test_questions = [
        "ВОККДЦ",  # Краткая форма
        "Что такое ВОККДЦ?",
        "VOKKDC",
        "VODC center",
        "Воронежский диагностический центр",
        "Воронежский областной клинический консультативно-диагностический центр",
        "ВОККДЦ Воронеж",
        "Адрес ВОККДЦ",
        "Телефон ВОККДЦ",
        "Как записаться в ВОККДЦ?",
        "Режим работы ВОККДЦ"
    ]
    
    for i, question in enumerate(test_questions, 1):
        print(f"{i}. ❓ {question}")
        try:
            response = bot.send_message(question)
            print(f"   🤖 Ответ: {response[:200]}...")  # Первые 200 символов
            print(f"   📊 Уверенность: {getattr(response, 'confidence', 'N/A')}")
            print(f"   📖 Источники: {getattr(response, 'sources', 'N/A')}")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
        print("-" * 60)
        print()

if __name__ == "__main__":
    test_abbreviations()