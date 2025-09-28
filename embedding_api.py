import requests
import json
from typing import List, Optional

class EmbeddingAPI:
    """API для генерации эмбеддингов через LM Studio"""
    
    def __init__(self, base_url: str = "http://localhost:1234"):
        self.base_url = base_url
        self.embedding_endpoint = f"{base_url}/v1/embeddings"
        self.models_endpoint = f"{base_url}/v1/models"
    
    def get_available_models(self) -> List[str]:
        """Получить список доступных моделей"""
        try:
            response = requests.get(self.models_endpoint)
            if response.status_code == 200:
                data = response.json()
                return [model["id"] for model in data.get("data", [])]
            else:
                print(f"Ошибка при получении списка моделей: {response.status_code}")
                return []
        except Exception as e:
            print(f"Ошибка при подключении к LM Studio: {e}")
            return []
    
    def get_embedding(self, text: str, model: str = None) -> Optional[List[float]]:
        """Получить эмбеддинг для текста"""
        try:
            payload = {
                "input": text,
                "model": model or "text-embedding-ada-002"  # Значение по умолчанию
            }
            
            response = requests.post(
                self.embedding_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                embedding = data.get("data", [{}])[0].get("embedding")
                return embedding
            else:
                print(f"Ошибка при генерации эмбеддинга: {response.status_code}")
                print(f"Ответ: {response.text}")
                return None
                
        except Exception as e:
            print(f"Ошибка при генерации эмбеддинга: {e}")
            return None
    
    def get_embeddings_batch(self, texts: List[str], model: str = None) -> List[Optional[List[float]]]:
        """Получить эмбеддинги для списка текстов"""
        embeddings = []
        for text in texts:
            embedding = self.get_embedding(text, model)
            embeddings.append(embedding)
        return embeddings

class MockEmbeddingAPI:
    """Мок-API для тестирования без LM Studio"""
    
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