# VODC AI Navigator

Минимальный MVP публичного информационного помощника ВОККДЦ. Система
подбирает подтверждённые материалы, услуги, врачей и свободное время, после
чего переводит пользователя в штатную форму записи. Она не ставит диагнозы,
не назначает лечение и не создаёт запись в МИС.

## Реализованный контур

- FastAPI и версионированный `/api/v1`, потоковые ответы SSE;
- детерминированная воронка и подписанные действия карточек;
- safety gateway до LLM и инструментов;
- Redis-сессии с TTL 2 часа;
- локальная очистка ПДн и хранение обезличенных данных 90 дней;
- PostgreSQL/pgvector и worker управляемой индексации;
- OpenAI-compatible vLLM gateway с двумя репликами;
- узкий адаптер API «МедАнгел» и безопасный fallback;
- адаптивный WCAG-ориентированный виджет;
- Prometheus/Grafana и анонимные события воронки.

Подробная схема находится в [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
а очищенная базовая линия — в
[docs/STAGE_0_BASELINE.md](docs/STAGE_0_BASELINE.md).
Требования, каталог намерений, воронка и KPI этапа 1 зафиксированы в
[docs/STAGE_1_REQUIREMENTS.md](docs/STAGE_1_REQUIREMENTS.md).
Архитектурные решения и модельный прототип этапа 2 описаны в
[docs/STAGE_2_ARCHITECTURE.md](docs/STAGE_2_ARCHITECTURE.md).
Локальный inference, GPU preflight, smoke и мониторинг этапа 3 описаны в
[docs/STAGE_3_INFERENCE.md](docs/STAGE_3_INFERENCE.md).

## Локальный запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 5000
```

Без `REDIS_URL` и `DATABASE_URL` включаются только локальные in-memory/JSON
адаптеры. Это режим разработки, а не production. Модель и МИС могут быть
недоступны; `/health/ready` показывает состояние каждой зависимости.

Виджет: `http://localhost:5000/`. OpenAPI: `http://localhost:5000/docs`.

## Проверки

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/run_policy_evals.py
.venv/bin/python scripts/check_architecture.py
.venv/bin/python scripts/inference_preflight.py
.venv/bin/python scripts/inference_smoke.py \
  --chat-url http://127.0.0.1:8000 \
  --chat-url http://127.0.0.1:8002 \
  --embedding-url http://127.0.0.1:8001
.venv/bin/python scripts/validate_retrieval_gold.py /secure/retrieval_gold.json
.venv/bin/python scripts/load_test.py --base-url https://chat.vodc.ru
.venv/bin/python scripts/smoke_test.py --base-url http://localhost:5000
```

Gold set должен содержать 100–200 утверждённых запросов и canonical URL.
Пример формата находится в `evals/retrieval_gold.example.json`.

## Production

1. Заполнить защищённый `.env` по `.env.production`.
2. Зафиксировать `VLLM_IMAGE` по одобренной версии или digest.
3. Согласовать mapping реального API «МедАнгел».
4. Заполнить allowlist источников и список приоритетов.
5. Выполнить `.venv/bin/python scripts/inference_preflight.py`.
6. Запустить `./deploy.sh`: он ждёт health-check, выполняет inference smoke,
   индексацию и требует успешный `/health/ready`.

Эксплуатационные процедуры описаны в
[docs/RUNBOOK.md](docs/RUNBOOK.md), а обязательные внешние входы — в
[docs/ACCEPTANCE_GAPS.md](docs/ACCEPTANCE_GAPS.md).
