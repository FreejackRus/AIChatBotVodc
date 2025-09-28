import os
import json
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import hashlib
from datetime import datetime

@dataclass
class Document:
    """Класс для хранения документа с метаданными"""
    content: str
    filename: str
    chunk_id: int
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None

class VectorStore:
    """Простое векторное хранилище для документов"""
    
    def __init__(self, storage_path: str = "knowledge_base"):
        self.storage_path = storage_path
        self.documents: List[Document] = []
        self.embeddings: List[List[float]] = []
        self.metadata = {
            "created_at": datetime.now().isoformat(),
            "total_documents": 0,
            "total_chunks": 0
        }
        
        # Создаем директорию для хранения
        os.makedirs(storage_path, exist_ok=True)
        self.load_from_disk()
    
    def add_document(self, document: Document):
        """Добавить документ в хранилище"""
        self.documents.append(document)
        if document.embedding:
            self.embeddings.append(document.embedding)
        self.metadata["total_documents"] += 1
        self.metadata["total_chunks"] += 1
        self.save_to_disk()
    
    def add_documents(self, documents: List[Document]):
        """Добавить несколько документов"""
        for doc in documents:
            self.add_document(doc)
    
    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Поиск похожих документов по эмбеддингу"""
        if not self.embeddings or not self.documents:
            return []
        
        # Вычисляем косинусное сходство
        similarities = []
        query_array = np.array(query_embedding)
        
        for i, embedding in enumerate(self.embeddings):
            doc_array = np.array(embedding)
            similarity = np.dot(query_array, doc_array) / (
                np.linalg.norm(query_array) * np.linalg.norm(doc_array)
            )
            similarities.append({
                "document": self.documents[i],
                "similarity": float(similarity),
                "index": i
            })
        
        # Сортируем по сходству и возвращаем топ-K
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return similarities[:top_k]
    
    def save_to_disk(self):
        """Сохранить хранилище на диск"""
        data = {
            "documents": [
                {
                    "content": doc.content,
                    "filename": doc.filename,
                    "chunk_id": doc.chunk_id,
                    "metadata": doc.metadata,
                    "embedding": doc.embedding
                }
                for doc in self.documents
            ],
            "metadata": self.metadata
        }
        
        with open(os.path.join(self.storage_path, "vector_store.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_from_disk(self):
        """Загрузить хранилище с диска"""
        store_path = os.path.join(self.storage_path, "vector_store.json")
        if os.path.exists(store_path):
            try:
                with open(store_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                self.documents = []
                self.embeddings = []
                
                for doc_data in data.get("documents", []):
                    doc = Document(
                        content=doc_data["content"],
                        filename=doc_data["filename"],
                        chunk_id=doc_data["chunk_id"],
                        metadata=doc_data["metadata"],
                        embedding=doc_data.get("embedding")
                    )
                    self.documents.append(doc)
                    if doc.embedding:
                        self.embeddings.append(doc.embedding)
                
                self.metadata.update(data.get("metadata", {}))
                
            except Exception as e:
                print(f"Ошибка при загрузке хранилища: {e}")
                self.documents = []
                self.embeddings = []

class DocumentProcessor:
    """Процессор для обработки и векторизации документов"""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text: str) -> List[str]:
        """Разбить текст на чанки с перекрытием"""
        if len(text) <= self.chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            # Находим конец чанка
            end = start + self.chunk_size
            
            # Если это не последний чанк, ищем границу слова
            if end < len(text):
                # Ищем последний пробел
                last_space = text.rfind(' ', start, end)
                if last_space != -1:
                    end = last_space
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Переходим к следующему чанку с перекрытием
            start = end - self.chunk_overlap
            
            # Защита от бесконечного цикла
            if start >= len(text):
                break
        
        return chunks
    
    def process_file(self, file_path: str) -> List[Document]:
        """Обработать файл и создать документы"""
        try:
            # Определяем тип файла
            if file_path.endswith('.txt'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif file_path.endswith('.md'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif file_path.endswith('.py'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            else:
                print(f"Формат файла {file_path} не поддерживается")
                return []
            
            # Создаем чанки
            chunks = self.chunk_text(content)
            documents = []
            
            for i, chunk in enumerate(chunks):
                doc = Document(
                    content=chunk,
                    filename=os.path.basename(file_path),
                    chunk_id=i,
                    metadata={
                        "file_path": file_path,
                        "chunk_size": len(chunk),
                        "total_chunks": len(chunks),
                        "file_size": len(content)
                    }
                )
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            print(f"Ошибка при обработке файла {file_path}: {e}")
            return []

class KnowledgeBase:
    """Основной класс для работы с базой знаний"""
    
    def __init__(self, storage_path: str = "knowledge_base"):
        self.vector_store = VectorStore(storage_path)
        self.processor = DocumentProcessor()
        self.storage_path = storage_path
        
        # Создаем директорию для документов
        self.docs_path = os.path.join(storage_path, "documents")
        os.makedirs(self.docs_path, exist_ok=True)
    
    def add_document_from_file(self, file_path: str, embedding_api=None) -> bool:
        """Добавить документ из файла в базу знаний"""
        if not os.path.exists(file_path):
            print(f"Файл {file_path} не найден")
            return False
        
        # Обрабатываем файл
        documents = self.processor.process_file(file_path)
        if not documents:
            return False
        
        # Генерируем эмбеддинги, если есть API
        if embedding_api:
            print(f"Генерирую эмбеддинги для {len(documents)} чанков...")
            for doc in documents:
                try:
                    embedding = embedding_api.get_embedding(doc.content)
                    doc.embedding = embedding
                except Exception as e:
                    print(f"Ошибка при генерации эмбеддинга: {e}")
        
        # Сохраняем документы
        self.vector_store.add_documents(documents)
        
        # Копируем файл в директорию документов
        import shutil
        filename = os.path.basename(file_path)
        dest_path = os.path.join(self.docs_path, filename)
        shutil.copy2(file_path, dest_path)
        
        print(f"Добавлено {len(documents)} чанков из файла {filename}")
        return True
    
    def search(self, query: str, embedding_api=None, top_k: int = 5) -> List[Dict[str, Any]]:
        """Поиск по базе знаний"""
        if not embedding_api:
            return []
        
        # Генерируем эмбеддинг для запроса
        try:
            query_embedding = embedding_api.get_embedding(query)
        except Exception as e:
            print(f"Ошибка при генерации эмбеддинга запроса: {e}")
            return []
        
        # Ищем похожие документы
        results = self.vector_store.search(query_embedding, top_k)
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику базы знаний"""
        return {
            "total_documents": len(set(doc.filename for doc in self.vector_store.documents)),
            "total_chunks": len(self.vector_store.documents),
            "storage_path": self.storage_path,
            "metadata": self.vector_store.metadata
        }
    
    def list_documents(self) -> List[str]:
        """Список всех документов в базе"""
        return list(set(doc.filename for doc in self.vector_store.documents))
    
    def clear(self):
        """Очистить базу знаний"""
        self.vector_store.documents = []
        self.vector_store.embeddings = []
        self.vector_store.metadata = {
            "created_at": datetime.now().isoformat(),
            "total_documents": 0,
            "total_chunks": 0
        }
        self.vector_store.save_to_disk()
        print("База знаний очищена")