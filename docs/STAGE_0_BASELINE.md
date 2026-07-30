# Этап 0. Базовая линия проекта

Статус репозитория: завершён. Инфраструктурная приёмка выполняется отдельно
на целевом сервере с 2×RTX 5090.

## Зафиксированная база

- единственный runtime-entrypoint: `app.main:app`;
- единственный backend: FastAPI с `/api/v1` и SSE;
- доменные правила не зависят от HTTP, PostgreSQL, Redis, vLLM и МИС;
- старые LM Studio CLI, Flask/Jivo compatibility, демонстрационные RAG-модули,
  корневые ручные тесты, IDE/cache-файлы и дубли документов удалены;
- локальные snapshots используются read-only fallback для разработки
  (старый embedding JSON удалён на этапе 4);
- production RAG использует PostgreSQL/pgvector;
- основная модель: `Qwen/Qwen3.5-9B`;
- embedding: `Qwen/Qwen3-Embedding-0.6B`;
- revision обеих моделей зафиксирован в `.env.example`, `.env.production`
  и `docker-compose.yml`;
- две независимые vLLM-реплики используют text-only режим, контекст 8192,
  максимум 10 последовательностей на реплику и FP8 KV cache;
- thinking mode отключён в OpenAI-compatible запросе backend.

## Локальные gates

- unit/API tests;
- safety/privacy policy evals;
- Python compile check;
- shell syntax check;
- `docker compose --profile gpu config`;
- `pip check`;
- `git diff --check`;
- проверка существования model ID и revision через Hugging Face Hub.

## Внешний gate

На сервере Заказчика остаются обязательными:

1. загрузка обоих checkpoint по зафиксированным revision;
2. старт chat- и embedding-процессов без OOM;
3. 20 диалогов × 10 сообщений и p95 начала ответа не более 10 секунд;
4. остановка одной реплики и подтверждение failover;
5. фиксация проверенного digest образа vLLM.

До прохождения этого gate нельзя утверждать, что локальный inference принят
для production, но это не блокирует этап 1 требований и доменной воронки.
