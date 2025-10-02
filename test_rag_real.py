#!/usr/bin/env python3
"""
Тестовый скрипт для проверки RAG системы с реальными эмбеддингами из Ollama
"""

from rag_system import RAGSystem

def test_rag_with_real_embeddings():
    """Тестируем RAG систему с реальными эмбеддингами"""
    print("🚀 Тестирование RAG системы с Ollama...")
    
    # Создаем RAG систему с реальными эмбеддингами
    print("📋 Инициализирую RAG систему с Ollama...")
    rag = RAGSystem(use_mock_embeddings=False)
    
    # Проверяем статистику
    stats = rag.get_stats()
    print(f"📊 Статистика базы знаний: {stats}")
    
    # Тестируем поиск
    print("🔍 Тестирую поиск...")
    query = "что такое ВОККДЦ"
    results = rag.search(query)
    
    print(f"✅ Найдено результатов: {len(results)}")
    
    if results:
        for i, result in enumerate(results[:3]):
            print(f"\n📄 Результат {i+1}:")
            print(f"   Контент: {result['content'][:150]}...")
            print(f"   Релевантность: {result['score']:.3f}")
    else:
        print("⚠️ Результаты не найдены")
    
    # Тестируем полный ответ
    print(f"\n🤖 Полный ответ на запрос '{query}':")
    response = rag.get_answer(query)
    
    print(f"\n💡 Ответ:")
    print(response['answer'])
    print(f"\n📖 Источники: {len(response['sources'])}")
    print(f"🎯 Уверенность: {response['confidence']:.3f}")

if __name__ == "__main__":
    test_rag_with_real_embeddings()