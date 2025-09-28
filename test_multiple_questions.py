#!/usr/bin/env python3
"""
Расширенное тестирование RAG системы с разными вопросами
"""

from rag_system import RAGSystem

def test_questions():
    # Создаем RAG систему
    print("Создаю RAG систему...")
    rag = RAGSystem(use_mock_embeddings=False)
    
    # Загружаем документы
    print("Загружаю документы...")
    rag.load_document('knowledge_base/vodc_complete_info.md')
    rag.load_document('knowledge_base/contacts_info.md')
    
    # Вопросы для тестирования
    questions = [
        "Как записаться к врачу в ВОККДЦ?",
        "Какие есть отделения в ВОККДЦ?",
        "Какие телефоны у ВОККДЦ?",
        "Где находится ВОККДЦ?",
        "Какие услуги предоставляет ВОККДЦ?"
    ]
    
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ ВОПРОСОВ И ОТВЕТОВ")
    print("="*60)
    
    for i, question in enumerate(questions, 1):
        print(f"\n{i}. ВОПРОС: {question}")
        print("-" * 50)
        
        response = rag.get_answer(question)
        print(f"ОТВЕТ: {response['answer']}")
        print(f"Уверенность: {response['confidence']:.3f}")
        print(f"Источников: {len(response['sources'])}")
        
        if response['sources']:
            print("Источники:")
            for source in response['sources'][:2]:
                print(f"  - {source['content'][:100]}...")

if __name__ == "__main__":
    test_questions()