# Архитектура MVP

Обоснования решений находятся в [ADR](adr/README.md), а проверяемый результат
этапа 2 — в [STAGE_2_ARCHITECTURE.md](STAGE_2_ARCHITECTURE.md).

```mermaid
flowchart LR
    W[Widget vodc.ru] -->|REST + SSE| A[FastAPI]
    A --> S[Safety gateway]
    S --> O[Dialog orchestrator]
    O --> K[RAG port]
    O --> M[MIS port]
    O --> L[Model port]
    A --> R[(Redis, raw session TTL 2h)]
    A --> D[PII redactor]
    D --> P[(PostgreSQL, redacted 90d)]
    K --> P
    M --> MA[MedAngel API]
    L --> V1[vLLM GPU 0]
    L --> V2[vLLM GPU 1]
    B[Worker] --> P
```

## Границы модулей

- `app/domain` — состояния, карточки, safety и бизнес-правила без I/O.
- `app/orchestrator.py` — порядок retrieval/tool/model вызовов.
- `app/ports.py` — внутренние контракты инфраструктуры.
- `app/adapters` — Redis, PostgreSQL, pgvector, vLLM и «МедАнгел».
- `app/main.py` — HTTP/SSE, CORS, rate limits, health и метрики.
- `app/worker.py` — переиндексация allowlist и удаление истёкших данных.

Направление зависимостей проверяет `scripts/check_architecture.py`. Domain,
ports, orchestrator и HTTP-слой не импортируют конкретные адаптеры.

LLM не меняет состояние воронки и не формирует параметры записи. Любое
действие карточки подписывается HMAC, привязано к сессии и повторно
проверяется по МИС. При отсутствии источников генерация не вызывается.
Каталог намерений и разрешения на обращения к RAG/МИС определены в
`app/domain/intents.py`; классификация выполняется детерминированно после
safety gateway и записывается только как обезличенное событие.

## Публичные интерфейсы

- `POST /api/v1/sessions`
- `POST /api/v1/sessions/{id}/messages/stream`
- `POST /api/v1/sessions/{id}/booking-link`
- `POST /api/v1/sessions/{id}/events`
- `GET /health/live`
- `GET /health/ready`

События SSE: `status`, `text_delta`, `sources`, `cards`, `state`, `error`,
`done`. Старый `/chat` намеренно отсутствует.

## Данные

Raw сообщения находятся только в Redis. В PostgreSQL записывается результат
локального redaction. В клиентской аналитике разрешены только фиксированные
события и свойства; произвольный текст отклоняется схемой API.
Redis работает без AOF/RDB, поэтому raw-сессии не попадают на диск и
теряются при перезапуске, что является ожидаемым безопасным поведением.

Цены, врачи и слоты всегда динамические данные МИС. RAG используется только
для утверждённых публичных материалов из `knowledge_base/sources.json`.
