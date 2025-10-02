import os
import requests
import json
from typing import List, Optional

class EmbeddingAPI:
    """API для генерации эмбеддингов через Ollama"""
    
    def __init__(self, base_url: str = None, embedding_model: Optional[str] = None):
        # Базовый URL берём из окружения или используем дефолт Ollama
        env_url = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_HOST")
        self.base_url = (base_url or env_url or "http://localhost:11434").rstrip("/")
        # Эндпоинты Ollama
        self.embedding_endpoint = f"{self.base_url}/api/embeddings"
        self.models_endpoint = f"{self.base_url}/api/tags"
        # Модель эмбеддингов
        self.embedding_model = embedding_model or os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей (тегов) из Ollama"""
        try:
            response = requests.get(self.models_endpoint, timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models") or data.get("data") or []
                names = []
                for model in models:
                    # Ollama возвращает список с ключом 'name'
                    name = model.get("name") or model.get("id") or model.get("model")
                    if name:
                        names.append(name)
                return names
            else:
                print(f"Ошибка при получении списка моделей: {response.status_code}")
                return []
        except Exception as e:
            print(f"Ошибка при подключении к Ollama: {e}")
            return []
    
    def get_embedding(self, text: str, model: Optional[str] = None) -> Optional[List[float]]:
        """Получить эмбеддинг для текста через Ollama /api/embeddings"""
        try:
            payload = {
                "model": model or self.embedding_model,
                "prompt": text
            }
            response = requests.post(
                self.embedding_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=20
            )
            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding")
                return embedding
            else:
                print(f"Ошибка при генерации эмбеддинга: {response.status_code}")
                print(f"Ответ: {response.text}")
                return None
        except Exception as e:
            print(f"Ошибка при генерации эмбеддинга: {e}")
            return None
    
    def get_embeddings_batch(self, texts: List[str], model: Optional[str] = None) -> List[Optional[List[float]]]:
        """Получить эмбеддинги для списка текстов (итеративно)"""
        embeddings = []
        for text in texts:
            embedding = self.get_embedding(text, model)
            embeddings.append(embedding)
        return embeddings

class MockEmbeddingAPI:
    """Мок-API для тестирования без Ollama"""
    
    def __init__(self, embedding_dim: int = 1536):
        self.embedding_dim = embedding_dim
    
    def get_embedding(self, text: str) -> List[float]:
        """Генерирует мок-эмбеддинг на основе хэша текста"""
        import hashlib
        import random
        
        # Используем хэш текста как seed для генерации последовательности
        hash_obj = hashlib.md5(text.encode())
        seed = int(hash_obj.hexdigest(), 16)
        random.seed(seed)
        
        # Генерируем эмбеддинг
        embedding = [random.gauss(0, 1) for _ in range(self.embedding_dim)]
        
        # Нормализуем вектор
        norm = sum(x**2 for x in embedding) ** 0.5
        if norm > 0:
            embedding = [x / norm for x in embedding]
        
        return embedding
    
    def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Генерирует мок-эмбеддинги для списка текстов"""
        return [self.get_embedding(text) for text in texts]