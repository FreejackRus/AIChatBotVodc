#!/usr/bin/env python3
"""
Тестирование вопросов и ответов с RAG системой
"""

from rag_system import RAGSystem

def test_qa():
    """Тестируем вопросы и ответы"""
    print("🚀 Тестирование вопросов и ответов...")
    
    # Создаем RAG систему с реальными эмбеддингами
    rag = RAGSystem(use_mock_embeddings=False)
    
    # Тестовые вопросы
    questions = [
        "Что такое ВОККДЦ и где он находится?",
        "Как записаться на прием?",
        "Какие услуги предоставляет центр?",
        "Какие есть контакты?",
        "Расскажи о центре"
    ]
    
    for question in questions:
        print(f"\n{'='*60}")
        print(f"❓ Вопрос: {question}")
        print(f"{'='*60}")
        
        response = rag.get_answer(question)
        
        print(f"💡 Ответ:")
        print(response['answer'])
        
        print(f"\n📊 Метрики:")
        print(f"   Уверенность: {response['confidence']:.3f}")
        print(f"   Источников: {len(response['sources'])}")
        
        if response['sources']:
            print(f"   Лучший источник (релевантность: {response['sources'][0]['score']:.3f}):")
            print(f"   {response['sources'][0]['content'][:150]}...")

if __name__ == "__main__":
    test_qa()