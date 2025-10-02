#!/usr/bin/env python3
"""
Тесты для интеграции с Ollama
"""

import unittest
import os
import sys
from unittest.mock import Mock, patch, MagicMock

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ollama_integration import OllamaAPI, OllamaRAGChatBot
from ollama_rag_system import OllamaRAGSystem

class TestOllamaAPI(unittest.TestCase):
    """Тесты для OllamaAPI класса"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.api = OllamaAPI()
    
    @patch('requests.get')
    def test_check_connection_success(self, mock_get):
        """Тест успешного подключения к Ollama"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"models": ["llama2", "mistral"]}
        mock_get.return_value = mock_response
        
        result = self.api.check_connection()
        self.assertTrue(result)
    
    @patch('requests.get')
    def test_check_connection_failure(self, mock_get):
        """Тест неудачного подключения к Ollama"""
        mock_get.side_effect = Exception("Connection refused")
        
        result = self.api.check_connection()
        self.assertFalse(result)
    
    @patch('requests.post')
    def test_generate_text_success(self, mock_post):
        """Тест успешной генерации текста"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Тестовый ответ от Ollama"
        }
        mock_post.return_value = mock_response
        
        result = self.api.generate_text("Привет, как дела?")
        self.assertEqual(result, "Тестовый ответ от Ollama")
    
    @patch('requests.post')
    def test_generate_text_with_context(self, mock_post):
        """Тест генерации текста с контекстом"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": "Ответ с учетом контекста"
        }
        mock_post.return_value = mock_response
        
        context = "Контекст: ВОККДЦ - это учебный центр"
        result = self.api.generate_text("Что такое ВОККДЦ?", context=context)
        self.assertEqual(result, "Ответ с учетом контекста")
    
    @patch('requests.get')
    def test_list_models_success(self, mock_get):
        """Тест получения списка моделей"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama2"},
                {"name": "mistral"},
                {"name": "codellama"}
            ]
        }
        mock_get.return_value = mock_response
        
        result = self.api.get_available_models()
        self.assertIn("llama2", result)
        self.assertIn("mistral", result)
    
    def test_get_model_info(self):
        """Тест получения информации о модели"""
        result = self.api.get_model_info()
        self.assertIsInstance(result, dict)
        self.assertIn("model", result)
        self.assertIn("host", result)


class TestOllamaRAGChatBot(unittest.TestCase):
    """Тесты для OllamaRAGChatBot класса"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.chatbot = OllamaRAGChatBot()
    
    @patch.object(OllamaAPI, 'check_connection')
    def test_initialization_with_ollama_available(self, mock_check):
        """Тест инициализации при доступном Ollama"""
        mock_check.return_value = True
        
        chatbot = OllamaRAGChatBot()
        self.assertTrue(chatbot.ollama_available)
        self.assertIsNotNone(chatbot.ollama_api)
    
    @patch.object(OllamaAPI, 'check_connection')
    def test_initialization_with_ollama_unavailable(self, mock_check):
        """Тест инициализации при недоступном Ollama"""
        mock_check.return_value = False
        
        chatbot = OllamaRAGChatBot()
        self.assertFalse(chatbot.ollama_available)
    
    @patch.object(OllamaAPI, 'generate_text')
    def test_chat_with_ollama_available(self, mock_generate):
        """Тест чата при доступном Ollama"""
        mock_generate.return_value = "Ответ от Ollama"
        
        result = self.chatbot.chat("Привет")
        self.assertIn("response", result)
        self.assertEqual(result["response"], "Ответ от Ollama")
        self.assertEqual(result["engine"], "ollama")
    
    def test_chat_with_ollama_unavailable(self):
        """Тест чата при недоступном Ollama"""
        # Создаем чатбота с недоступным Ollama
        with patch.object(OllamaAPI, 'check_connection', return_value=False):
            chatbot = OllamaRAGChatBot()
        
        result = chatbot.chat("Привет")
        self.assertIn("response", result)
        self.assertEqual(result["engine"], "ollama")
        self.assertIn("error", result)


class TestOllamaRAGSystem(unittest.TestCase):
    """Тесты для OllamaRAGSystem класса"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.rag_system = OllamaRAGSystem()
    
    def test_chunk_text(self):
        """Тест разбиения текста на чанки"""
        text = "Это длинный текст который нужно разбить на несколько частей. " * 50
        chunks = self.rag_system.chunk_text(text)
        
        self.assertIsInstance(chunks, list)
        self.assertGreater(len(chunks), 1)
        self.assertLess(len(chunks[0]), len(text))
    
    @patch.object(OllamaAPI, 'generate_text')
    def test_generate_embedding(self, mock_generate):
        """Тест генерации эмбеддингов"""
        mock_generate.return_value = "[0.1, 0.2, 0.3, 0.4, 0.5]"
        
        result = self.rag_system.generate_embedding("Тестовый текст")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 5)
    
    def test_find_similar_chunks(self):
        """Тест поиска похожих чанков"""
        # Добавляем тестовые данные
        self.rag_system.vector_store = {
            "chunk1": {"text": "ВОККДЦ - это учебный центр", "embedding": [0.1, 0.2, 0.3]},
            "chunk2": {"text": "Курсы программирования", "embedding": [0.4, 0.5, 0.6]},
            "chunk3": {"text": "Образовательные программы", "embedding": [0.7, 0.8, 0.9]}
        }
        
        query_embedding = [0.1, 0.2, 0.3]
        results = self.rag_system.find_similar_chunks(query_embedding, top_k=2)
        
        self.assertIsInstance(results, list)
        self.assertLessEqual(len(results), 2)
    
    @patch.object(OllamaAPI, 'generate_text')
    def test_generate_response_with_context(self, mock_generate):
        """Тест генерации ответа с контекстом"""
        mock_generate.return_value = "Информативный ответ"
        
        context = "ВОККДЦ - это учебный центр"
        query = "Что такое ВОККДЦ?"
        
        result = self.rag_system.generate_response_with_context(query, context)
        self.assertEqual(result, "Информативный ответ")
    
    def test_save_and_load_vector_store(self):
        """Тест сохранения и загрузки векторного хранилища"""
        # Добавляем тестовые данные
        test_data = {"test_chunk": {"text": "Тест", "embedding": [0.1, 0.2]}}
        self.rag_system.vector_store = test_data
        
        # Сохраняем
        self.rag_system.save_vector_store("test_store.json")
        
        # Загружаем в новый экземпляр
        new_system = OllamaRAGSystem()
        new_system.load_vector_store("test_store.json")
        
        self.assertEqual(new_system.vector_store, test_data)
        
        # Очищаем
        if os.path.exists("test_store.json"):
            os.remove("test_store.json")


class TestOllamaIntegration(unittest.TestCase):
    """Интеграционные тесты для Ollama"""
    
    @patch.object(OllamaAPI, 'check_connection')
    @patch.object(OllamaAPI, 'generate_text')
    def test_full_rag_workflow(self, mock_generate, mock_check):
        """Тест полного RAG рабочего процесса"""
        mock_check.return_value = True
        mock_generate.return_value = "ВОККДЦ предлагает курсы программирования"
        
        # Создаем RAG систему
        rag_system = OllamaRAGSystem()
        
        # Добавляем знания
        documents = [
            "ВОККДЦ - это учебный центр в Москве",
            "Мы предлагаем курсы программирования на Python и JavaScript",
            "Обучение проходит в малых группах с опытными преподавателями"
        ]
        
        for doc in documents:
            chunks = rag_system.chunk_text(doc)
            for chunk in chunks:
                embedding = rag_system.generate_embedding(chunk)
                rag_system.vector_store[f"doc_{len(rag_system.vector_store)}"] = {
                    "text": chunk,
                    "embedding": embedding
                }
        
        # Тестируем запрос
        query = "Что вы предлагаете?"
        query_embedding = rag_system.generate_embedding(query)
        
        # Ищем похожие документы
        similar_docs = rag_system.find_similar_chunks(query_embedding)
        
        # Генерируем ответ
        if similar_docs:
            context = " ".join([doc["text"] for doc in similar_docs[:3]])
            response = rag_system.generate_response_with_context(query, context)
            
            self.assertIsInstance(response, str)
            self.assertGreater(len(response), 0)


if __name__ == '__main__':
    # Запускаем тесты
    unittest.main(verbosity=2)