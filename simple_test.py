#!/usr/bin/env python3
"""
Простое тестирование RAG системы
"""

from rag_system import RAGSystem

def main():
    # Создаем RAG систему с реальными эмбеддингами
    print("Создаю RAG систему с Ollama...")
    rag = RAGSystem(use_mock_embeddings=False)
    
    # Загружаем документ
    print("Загружаю документ...")
    success = rag.load_document('knowledge_base/vodc_complete_info.md')
    
    if success:
        print("Документ загружен успешно!")
        
        # Тестируем поиск
        print("\nТестирую поиск...")
        results = rag.search('что такое ВОККДЦ')
        print(f"Найдено результатов: {len(results)}")
        
        # Тестируем ответ
        print("\nТестирую ответ...")
        response = rag.get_answer('что такое ВОККДЦ')
        print(f"Ответ: {response['answer']}")
        print(f"Уверенность: {response['confidence']}")
        print(f"Источников: {len(response['sources'])}")
    else:
        print("Ошибка загрузки документа")

if __name__ == "__main__":
    main()