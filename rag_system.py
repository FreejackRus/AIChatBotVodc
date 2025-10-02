"""
RAG (Retrieval-Augmented Generation) система для ВОККДЦ
Объединяет поиск по базе знаний и генерацию ответов
"""

import os
import json
from typing import List, Dict, Any, Optional
from knowledge_base import KnowledgeBase
from embedding_api import EmbeddingAPI, MockEmbeddingAPI


class RAGSystem:
    """RAG система для поиска и генерации ответов на основе базы знаний"""
    
    def __init__(self, use_mock_embeddings: bool = False):
        """Инициализация RAG-системы"""
        self.knowledge_base = KnowledgeBase()
        
        if use_mock_embeddings:
            self.embedding_api = MockEmbeddingAPI()
        else:
            # Используем реальный API для эмбеддингов из Ollama
            try:
                self.embedding_api = EmbeddingAPI()
                print("✓ Подключение к Ollama для эмбеддингов")
            except Exception as e:
                print(f"⚠️ Не удалось подключиться к Ollama: {e}")
                print("✓ Используются моковые эмбеддинги")
                self.embedding_api = MockEmbeddingAPI()
        
        self.documents_loaded = False
        print("✓ RAG-система для ВОККДЦ инициализирована")
    
    def load_document(self, file_path: str) -> bool:
        """Загрузить документ в базу знаний"""
        try:
            if not os.path.exists(file_path):
                print(f"❌ Файл не найден: {file_path}")
                return False
            
            print(f"📄 Загрузка документа: {file_path}")
            success = self.knowledge_base.add_document_from_file(file_path, self.embedding_api)
            
            if success:
                self.documents_loaded = True
                stats = self.knowledge_base.get_stats()
                print(f"✓ Документ загружен успешно")
                print(f"  📊 Всего документов: {stats['total_documents']}")
                print(f"  📄 Всего фрагментов: {stats['total_chunks']}")
                return True
            else:
                print("❌ Ошибка при загрузке документа")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка при загрузке документа: {e}")
            return False
    
    def search(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        """Поиск по базе знаний"""
        if not self.documents_loaded:
            print("⚠️ База знаний пустая. Сначала загрузите документы.")
            return []
        
        try:
            results = self.knowledge_base.search(query, self.embedding_api, top_k=k)
            
            formatted_results = []
            for result in results:
                formatted_results.append({
                    'content': result['document'].content,
                    'score': result['similarity'],
                    'metadata': result['document'].metadata
                })
            
            return formatted_results
            
        except Exception as e:
            print(f"❌ Ошибка при поиске: {e}")
            return []
    
    def get_answer(self, query: str, k: int = 3) -> Dict[str, Any]:
        """Получить ответ на вопрос на основе поиска"""
        search_results = self.search(query, k=k)
        
        if not search_results:
            return {
                'answer': 'Извините, я не нашел релевантной информации в базе знаний ВОККДЦ.',
                'sources': [],
                'confidence': 0.0
            }
        
        # Формируем контекст из найденных результатов
        context = ""
        sources = []
        
        for i, result in enumerate(search_results):
            context += f"[Источник {i+1}] {result['content']}\n\n"
            sources.append({
                'content': result['content'][:200] + '...' if len(result['content']) > 200 else result['content'],
                'score': result['score']
            })
        
        # Простая генерация ответа на основе контекста
        # В реальном приложении здесь был бы вызов LLM
        answer = self._generate_simple_answer(query, context)
        
        # Оцениваем уверенность на основе score'ов
        avg_score = sum(result['score'] for result in search_results) / len(search_results)
        confidence = min(avg_score * 1.2, 1.0)  # Нормализуем до 1.0
        
        return {
            'answer': answer,
            'sources': sources,
            'confidence': confidence
        }
    
    def _generate_simple_answer(self, query: str, context: str) -> str:
        """Простая генерация ответа на основе контекста (заглушка для LLM)"""
        # Это упрощенная версия - в реальном приложении здесь был бы вызов LLM
        
        # Извлекаем релевантные части контекста
        lines = context.split('\n')
        relevant_lines = []
        
        for line in lines:
            if len(line.strip()) > 20:  # Берем только содержательные строки
                relevant_lines.append(line.strip())
        
        # Формируем ответ
        answer = f"На основе информации из базы знаний ВОККДЦ:\n\n"
        
        # Добавляем наиболее релевантные части
        for i, line in enumerate(relevant_lines[:4]):  # Берем первые 4 содержательные строки
            if i == 0:
                answer += f"• {line}\n"
            else:
                answer += f"• {line}\n"
        
        answer += f"\nДля более подробной информации рекомендую обратиться в регистратуру ВОККДЦ по телефону +7 (473) 272-02-05."
        
        return answer
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику базы знаний"""
        return self.knowledge_base.get_stats()
    
    def clear_knowledge_base(self) -> bool:
        """Очистить базу знаний"""
        try:
            self.knowledge_base.clear()
            self.documents_loaded = False
            print("✓ База знаний очищена")
            return True
        except Exception as e:
            print(f"❌ Ошибка при очистке базы знаний: {e}")
            return False