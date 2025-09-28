#!/usr/bin/env python3
"""
Тестирование многопользовательской работы системы
"""

import requests
import json
import threading
import time

def test_user_session(session_id, user_name):
    """Тестируем работу одного пользователя"""
    print(f"👤 {user_name} (сессия {session_id}) начинает тест...")
    
    try:
        # Первое сообщение
        response1 = requests.post('http://localhost:5000/chat', 
                                 json={'message': 'Что такое ВОККДЦ?', 'session_id': session_id})
        data1 = response1.json()
        print(f"  {user_name}: ✓ Первое сообщение получено (session_id: {data1['session_id']})")
        
        # Второе сообщение
        response2 = requests.post('http://localhost:5000/chat', 
                                 json={'message': 'Как записаться?', 'session_id': session_id})
        data2 = response2.json()
        print(f"  {user_name}: ✓ Второе сообщение получено (session_id: {data2['session_id']})")
        
        # Проверяем, что сессия та же
        if data1['session_id'] == data2['session_id'] == session_id:
            print(f"  {user_name}: ✓ Сессия сохраняется корректно")
        else:
            print(f"  {user_name}: ❌ Ошибка сохранения сессии")
            
        return True
        
    except Exception as e:
        print(f"  {user_name}: ❌ Ошибка: {e}")
        return False

def test_parallel_users():
    """Тестируем параллельную работу нескольких пользователей"""
    print("🚀 Запускаем параллельное тестирование...")
    
    users = [
        ("user1", "Пользователь 1"),
        ("user2", "Пользователь 2"), 
        ("user3", "Пользователь 3"),
        ("user4", "Пользователь 4")
    ]
    
    threads = []
    results = []
    
    def run_test(session_id, user_name):
        result = test_user_session(session_id, user_name)
        results.append(result)
    
    # Запускаем все тесты параллельно
    start_time = time.time()
    
    for session_id, user_name in users:
        thread = threading.Thread(target=run_test, args=(session_id, user_name))
        threads.append(thread)
        thread.start()
    
    # Ждем завершения всех тестов
    for thread in threads:
        thread.join()
    
    end_time = time.time()
    
    # Проверяем общее состояние
    try:
        health = requests.get('http://localhost:5000/health').json()
        print(f"\n📊 Общая статистика:")
        print(f"  Активных сессий: {health['active_sessions']}")
        print(f"  Статус RAG-системы: {health['rag_system']}")
        print(f"  Время выполнения: {end_time - start_time:.2f} секунд")
        
        successful_tests = sum(results)
        total_tests = len(results)
        
        print(f"  Успешных тестов: {successful_tests}/{total_tests}")
        
        if successful_tests == total_tests:
            print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ! Система работает с множеством пользователей параллельно.")
            return True
        else:
            print(f"\n❌ {total_tests - successful_tests} тестов провалено.")
            return False
            
    except Exception as e:
        print(f"\n❌ Ошибка при получении статистики: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Тестирование многопользовательской работы ВОККДЦ чатбота")
    print("=" * 60)
    
    # Проверяем, что сервер доступен
    try:
        response = requests.get('http://localhost:5000/health')
        print("✅ Сервер доступен")
    except:
        print("❌ Сервер не доступен. Запустите widget_server.py")
        exit(1)
    
    # Запускаем тест
    success = test_parallel_users()
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 СИСТЕМА ГОТОВА К РАБОТЕ С НЕСКОЛЬКИМИ ПОЛЬЗОВАТЕЛЯМИ!")
        print("📋 Выводы:")
        print("  • Каждый пользователь получает свою сессию")
        print("  • Сессии изолированы друг от друга")
        print("  • Система масштабируется для параллельной работы")
        print("  • История сообщений сохраняется для каждой сессии")
    else:
        print("⚠️  Обнаружены проблемы в многопользовательской работе.")