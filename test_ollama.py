#!/usr/bin/env python3
"""
Тесты для Ollama интеграции
"""

import unittest
import os
import sys
import json
from unittest.mock import Mock, patch

# Добавляем путь к проекту
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ollama_integration import OllamaAPI, OllamaRAGChatBot
from ollama_rag_system import OllamaRAGSystem

class TestOllamaAPI(unittest.TestCase):
    """Тесты для OllamaAPI"""
    
    def setUp(self):
        self.api = OllamaAPI()
    
    def test_initialization(self):
        """Тест инициализации API"""
        self.assertIsNotNone(self.api)
        self.assertTrue(hasattr(self.api, 'base_url'))
        self.assertTrue(hasattr(self.api, 'model'))
    
    @patch('requests.post')
    def test_check_connection_success(self, mock_post):
        """Тест успешного подключения"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'status': 'success'}
        
        result = self.api.check_connection()
        self.assertTrue(result)
    
    @patch('requests.post')
    def test_generate_text_success(self, mock_post):
        """Тест успешной генерации текста"""
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'response': 'Тестовый ответ'
        }
        
        result = self.api.generate_text('Тестовый запрос')
        self.assertEqual(result, 'Тестовый ответ')
    
    def test_get_model_info(self):
        """Тест получения информации о модели"""
        info = self.api.get_model_info()
        self.assertIsInstance(info, dict)

class TestOllamaRAGChatBot(unittest.TestCase):
    """Тесты для OllamaRAGChatBot"""
    
    def setUp(self):
        self.ollama_api = OllamaAPI()
        self.chatbot = OllamaRAGChatBot(ollama_api=self.ollama_api)
    
    def test_initialization(self):
        """Тест инициализации чат-бота"""
        self.assertIsNotNone(self.chatbot)
        self.assertTrue(hasattr(self.chatbot, 'ollama'))

class TestOllamaRAGSystem(unittest.TestCase):
    """Тесты для OllamaRAGSystem"""
    
    def setUp(self):
        self.ollama_api = OllamaAPI()
        self.rag_system = OllamaRAGSystem(ollama_api=self.ollama_api)
    
    def test_initialization(self):
        """Тест инициализации RAG системы"""
        self.assertIsNotNone(self.rag_system)
        self.assertTrue(hasattr(self.rag_system, 'ollama'))
        self.assertTrue(hasattr(self.rag_system, 'chunks'))
    
    def test_chunk_text(self):
        """Тест разбиения текста на чанки"""
        text = "Это первое предложение. Это второе предложение. Это третье предложение."
        chunks = self.rag_system.chunk_text(text, chunk_size=50)
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 0)
    
    def test_create_embeddings_ollama(self):
        """Тест создания эмбеддингов"""
        texts = ["Тестовый текст 1", "Тестовый текст 2"]
        embeddings = self.rag_system.create_embeddings_ollama(texts)
        
        self.assertIsInstance(embeddings, list)
        self.assertEqual(len(embeddings), 2)
        self.assertIsInstance(embeddings[0], list)
    
    def test_search_similar_chunks_empty(self):
        """Тест поиска в пустой базе"""
        result = self.rag_system.search_similar_chunks("тестовый запрос")
        self.assertEqual(result, [])
    
    def test_generate_response_no_context(self):
        """Тест генерации ответа без контекста"""
        result = self.rag_system.generate_response("тестовый запрос", [])
        self.assertIn("Извините", result)

class TestIntegration(unittest.TestCase):
    """Интеграционные тесты"""
    
    def test_full_workflow(self):
        """Тест полного рабочего процесса"""
        # Создаем API
        api = OllamaAPI()
        
        # Создаем RAG систему
        rag_system = OllamaRAGSystem(ollama_api=api)
        
        # Проверяем, что все компоненты работают
        self.assertIsNotNone(api)
        self.assertIsNotNone(rag_system)
        
        # Тестируем чат-бота
        chatbot = OllamaRAGChatBot(ollama_api=api)
        self.assertIsNotNone(chatbot)

if __name__ == '__main__':
    print("🧪 Запуск тестов Ollama интеграции...")
    unittest.main(verbosity=2)