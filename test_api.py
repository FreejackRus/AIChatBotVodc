#!/usr/bin/env python3
"""
Тестирование API чатбота ВОККДЦ
"""

import requests
import json

def test_chatbot():
    """Тестируем чатбота через API"""
    url = "http://localhost:8085/chat"
    
    test_questions = [
        "ВОККДЦ",
        "воккдц",
        "Что такое ВОККДЦ?",
        "Адрес ВОККДЦ",
        "Телефон ВОККДЦ",
        "Как записаться в ВОККДЦ?",
        "VOKKDC",
        "Режим работы ВОККДЦ"
    ]
    
    print("🧪 Тестирование API чатбота ВОККДЦ:")
    print("=" * 60)
    
    for question in test_questions:
        try:
            payload = {
                "message": question
            }
            
            response = requests.post(url, json=payload)
            
            if response.status_code == 200:
                result = response.json()
                print(f"\n❓ Вопрос: {question}")
                print(f"🤖 Ответ: {result.get('response', 'Нет ответа')[:200]}...")
                print(f"📊 Уверенность: {result.get('confidence', 'N/A')}")
                print(f"📖 Источники: {result.get('sources', 'N/A')}")
                print(f"🔄 RAG доступен: {result.get('rag_available', False)}")
            else:
                print(f"❌ Ошибка для вопроса '{question}': {response.status_code}")
                print(response.text)
                
        except Exception as e:
            print(f"❌ Исключение для вопроса '{question}': {e}")
        
        print("-" * 40)

if __name__ == "__main__":
    test_chatbot()