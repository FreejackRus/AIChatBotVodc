import json
import math
import random
from typing import List, Dict, Any, Optional, Tuple
import os
from dataclasses import dataclass
import re
from ollama_integration import OllamaAPI, OllamaRAGChatBot

@dataclass
class DocumentChunk:
    """Класс для хранения чанков документов"""
    text: str
    source: str
    chunk_id: int
    embedding: Optional[List[float]] = None

class OllamaRAGSystem:
    """RAG система с использованием Ollama для генерации эмбеддингов и ответов"""
    
    def __init__(self, ollama_api: OllamaAPI, embedding_model: str = "nomic-embed-text", 
                 knowledge_base_path: str = "knowledge_base"):
        self.ollama = ollama_api
        self.embedding_model = embedding_model
        self.knowledge_base_path = knowledge_base_path
        self.vector_store_file = os.path.join(knowledge_base_path, "vector_store.json")
        self.documents = []
        self.chunks = []
        self.embeddings = []
        
        # Создаем директорию для базы знаний, если её нет
        os.makedirs(knowledge_base_path, exist_ok=True)
        
        # Загружаем существующую векторную базу
        self.load_vector_store()
    
    def create_embeddings_ollama(self, texts: List[str]) -> List[List[float]]:
        """Создание эмбеддингов через Ollama"""
        embeddings = []
        
        for text in texts:
            try:
                # Используем generate API для создания эмбеддингов
                # Ollama не имеет отдельного endpoint для эмбеддингов,
                # поэтому используем generate с системным промптом
                # В реальности нужно использовать модель эмбеддингов
                # Пока используем упрощенный подход
                _ = self.ollama.generate_text(
                    prompt=f"Convert this text to numerical embedding representation: {text}",
                    system_prompt="You are an embedding model. Return only numerical values."
                )
                
                # Заглушка для эмбеддингов (в продакшене нужно использовать настоящую модель эмбеддингов)
                # Создаем случайный вектор нужной размерности для демонстрации
                embedding = [random.gauss(0.0, 1.0) for _ in range(384)]  # Размерность как у all-MiniLM-L6-v2
                embeddings.append(embedding)
                
            except Exception as e:
                print(f"Ошибка при создании эмбеддинга: {e}")
                # Возвращаем нулевой вектор в случае ошибки
                embeddings.append([0.0] * 384)
        
        return embeddings
    
    def chunk_text(self, text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> List[str]:
        """Разбиение текста на чанки"""
        # Простое разбиение по предложениям
        sentences = re.split(r'[.!?]+', text)
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks if chunks else [text]
    
    def add_document(self, file_path: str, content: str = None) -> bool:
        """Добавление документа в базу знаний"""
        try:
            # Чтение файла или использование предоставленного контента
            if content is None:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # Разбиение на чанки
            chunks = self.chunk_text(content)
            
            # Создание эмбеддингов для чанков
            chunk_embeddings = self.create_embeddings_ollama(chunks)
            
            # Сохранение чанков
            for i, (chunk_text, embedding) in enumerate(zip(chunks, chunk_embeddings)):
                chunk = DocumentChunk(
                    text=chunk_text,
                    source=file_path,
                    chunk_id=i,
                    embedding=embedding
                )
                self.chunks.append(chunk)
                self.embeddings.append(embedding)
            
            print(f"✅ Добавлен документ: {file_path}")
            print(f"📊 Создано {len(chunks)} чанков")
            
            # Сохранение векторной базы
            self.save_vector_store()
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка при добавлении документа: {e}")
            return False
    
    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        # Косинусное сходство без numpy/sklearn
        if not a or not b or len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot_product / (norm_a * norm_b)
    
    def search_similar_chunks(self, query: str, top_k: int = 5) -> List[Tuple[DocumentChunk, float]]:
        """Поиск похожих чанков"""
        if not self.chunks:
            return []
        
        try:
            # Создание эмбеддинга для запроса
            query_embedding = self.create_embeddings_ollama([query])[0]
            
            # Вычисление сходства
            similarities = []
            for i, chunk in enumerate(self.chunks):
                similarity = self._cosine_similarity(query_embedding, chunk.embedding)
                similarities.append((chunk, similarity))
            
            # Сортировка по сходству
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            return similarities[:top_k]
            
        except Exception as e:
            print(f"❌ Ошибка при поиске: {e}")
            return []
    
    def generate_response(self, query: str, context_chunks: List[DocumentChunk]) -> str:
        """Генерация ответа на основе контекста"""
        print(f"🔄 Начинаю генерацию ответа для запроса: {query[:50]}...")
        
        if not context_chunks:
            print("⚠️ Нет контекстных чанков для генерации ответа")
            return "Извините, я не нашел релевантной информации для ответа на ваш вопрос."
        
        print(f"📚 Найдено {len(context_chunks)} контекстных чанков")
        
        # Формирование контекста
        context_text = "\n\n".join([chunk.text for chunk in context_chunks])
        print(f"📝 Длина контекста: {len(context_text)} символов")
        
        # Создание промпта для Ollama
        prompt = f"""Ты - помощник Воронежского областного клинико-диагностического центра (ВОККДЦ).
        Используй следующую информацию из базы знаний ВОККДЦ для ответа на вопрос пациента:

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ:
        {context_text}

        ВОПРОС ПАЦИЕНТА:
        {query}

        ИНСТРУКЦИИ:
        1. Отвечай только на русском языке.
        2. Будь вежливым и профессиональным.
        3. Используй только информацию из контекста.
        4. Если в контексте нет ответа, честно скажи об этом.
        5. Предложи обратиться на горячую линию ВОККДЦ: +7 (473) 202-22-22.
        6. Не добавляй приветствие, обращения или формальные подписи. Сразу отвечай по сути.

        ОТВЕТ:"""
        
        print(f"📤 Отправляю промпт в Ollama (длина: {len(prompt)} символов)")
        
        try:
            response = self.ollama.generate_text(
                prompt=prompt,
                temperature=0.3,  # Низкая температура для более точных ответов
                max_tokens=1024
            )
            
            print(f"✅ Получен ответ от Ollama (длина: {len(response)} символов)")
            print(f"🔍 Первые 100 символов ответа: {response[:100]}...")
            
            return response.strip()
            
        except Exception as e:
            print(f"❌ Ошибка при генерации ответа: {e}")
            return f"Извините, произошла ошибка при генерации ответа: {str(e)}"
    
    def query(self, query: str, top_k: int = 5) -> Dict[str, Any]:
        """Основной метод для обработки запроса"""
        try:
            # Поиск релевантных чанков
            similar_chunks = self.search_similar_chunks(query, top_k)
            
            if not similar_chunks:
                return {
                    "response": "Извините, я не нашел релевантной информации для ответа на ваш вопрос.",
                    "sources": [],
                    "confidence": 0.0
                }
            
            # Извлечение чанков и оценок сходства
            chunks = [chunk for chunk, _ in similar_chunks]
            similarities = [sim for _, sim in similar_chunks]
            
            # Генерация ответа
            response = self.generate_response(query, chunks)
            
            # Подготовка источников
            sources = []
            for chunk, similarity in similar_chunks:
                sources.append({
                    "file": chunk.source,
                    "chunk_id": chunk.chunk_id,
                    "similarity": round(similarity, 3),
                    "text": chunk.text[:200] + "..." if len(chunk.text) > 200 else chunk.text
                })
            
            # Расчет уверенности (средняя схожесть)
            confidence = (sum(similarities) / len(similarities)) if similarities else 0.0
            
            return {
                "response": response,
                "sources": sources,
                "confidence": round(confidence, 3)
            }
            
        except Exception as e:
            return {
                "response": f"Извините, произошла ошибка при обработке запроса: {str(e)}",
                "sources": [],
                "confidence": 0.0
            }

    def stream_query(self, query: str, top_k: int = 5):
        """Потоковая обработка запроса: сначала отдаём метаданные, затем токены ответа.

        Возвращает генератор событий-словарей вида:
        - {"type": "meta", "sources": [...], "confidence": float}
        - {"type": "token", "text": str}
        - {"type": "done", "response": str}
        """
        try:
            # Поиск релевантных чанков
            similar_chunks = self.search_similar_chunks(query, top_k)

            if not similar_chunks:
                yield {
                    "type": "meta",
                    "sources": [],
                    "confidence": 0.0
                }
                yield {
                    "type": "done",
                    "response": "Извините, я не нашел релевантной информации для ответа на ваш вопрос."
                }
                return

            # Извлечение чанков и оценок сходства
            chunks = [chunk for chunk, _ in similar_chunks]
            similarities = [sim for _, sim in similar_chunks]

            # Формирование источников и уверенности
            sources = []
            for chunk, similarity in similar_chunks:
                sources.append({
                    "file": chunk.source,
                    "chunk_id": chunk.chunk_id,
                    "similarity": round(similarity, 3),
                    "text": chunk.text[:200] + "..." if len(chunk.text) > 200 else chunk.text
                })
            confidence = (sum(similarities) / len(similarities)) if similarities else 0.0

            # Отправляем метаданные первыми
            yield {
                "type": "meta",
                "sources": sources,
                "confidence": round(confidence, 3)
            }

            # Создание промпта как в generate_response
            context_text = "\n\n".join([chunk.text for chunk in context_chunks]) if (context_chunks := chunks) else ""
            prompt = f"""Ты - помощник Воронежского областного клинико-диагностического центра (ВОККДЦ).
        Используй следующую информацию из базы знаний ВОККДЦ для ответа на вопрос пациента:

        КОНТЕКСТ ИЗ БАЗЫ ЗНАНИЙ:
        {context_text}

        ВОПРОС ПАЦИЕНТА:
        {query}

        ИНСТРУКЦИИ:
        1. Отвечай только на русском языке.
        2. Будь вежливым и профессиональным.
        3. Используй только информацию из контекста.
        4. Если в контексте нет ответа, честно скажи об этом.
        5. Предложи обратиться на горячую линию ВОККДЦ: +7 (473) 202-22-22.
        6. Не добавляй приветствие, обращения или формальные подписи. Сразу отвечай по сути.

        ОТВЕТ:"""

            # Потоковая генерация текста через Ollama
            accumulated = []
            try:
                for chunk in self.ollama.stream_generate_text(
                    prompt=prompt,
                    temperature=0.3,
                    max_tokens=1024
                ):
                    text = chunk.get("response") or chunk.get("text") or ""
                    if text:
                        accumulated.append(text)
                        yield {"type": "token", "text": text}

                final_text = ("".join(accumulated)).strip()
                yield {"type": "done", "response": final_text}
            except Exception as e:
                yield {"type": "done", "response": f"Извините, произошла ошибка при генерации ответа: {str(e)}"}
        except Exception as e:
            # Общая ошибка
            yield {"type": "meta", "sources": [], "confidence": 0.0}
            yield {"type": "done", "response": f"Извините, произошла ошибка при обработке запроса: {str(e)}"}
    
    def save_vector_store(self):
        """Сохранение векторной базы в файл"""
        try:
            data = {
                "chunks": [
                    {
                        "text": chunk.text,
                        "source": chunk.source,
                        "chunk_id": chunk.chunk_id,
                        "embedding": chunk.embedding
                    }
                    for chunk in self.chunks
                ]
            }
            
            with open(self.vector_store_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            print(f"💾 Векторная база сохранена: {len(self.chunks)} чанков")
            
        except Exception as e:
            print(f"❌ Ошибка при сохранении векторной базы: {e}")
    
    def load_vector_store(self):
        """Загрузка векторной базы из файла"""
        try:
            if os.path.exists(self.vector_store_file):
                with open(self.vector_store_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.chunks = []
                self.embeddings = []
                
                for chunk_data in data.get('chunks', []):
                    chunk = DocumentChunk(
                        text=chunk_data['text'],
                        source=chunk_data['source'],
                        chunk_id=chunk_data['chunk_id'],
                        embedding=chunk_data['embedding']
                    )
                    self.chunks.append(chunk)
                    self.embeddings.append(chunk_data['embedding'])
                
                print(f"📂 Загружена векторная база: {len(self.chunks)} чанков")
                
            else:
                print("📂 Векторная база не найдена, будет создана при добавлении документов")
                
        except Exception as e:
            print(f"❌ Ошибка при загрузке векторной базы: {e}")
            self.chunks = []
            self.embeddings = []
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики по базе знаний"""
        total_chunks = len(self.chunks)
        total_sources = len(set(chunk.source for chunk in self.chunks))
        
        # Подсчет символов
        total_chars = sum(len(chunk.text) for chunk in self.chunks)
        
        return {
            "total_chunks": total_chunks,
            "total_sources": total_sources,
            "total_characters": total_chars,
            "embedding_model": self.embedding_model,
            "vector_store_file": self.vector_store_file
        }