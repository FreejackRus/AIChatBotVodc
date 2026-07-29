# Runbook

## Запуск и обновление

```bash
.venv/bin/python scripts/inference_preflight.py
./deploy.sh
curl --fail https://chat.vodc.ru/health/ready
```

`ready` обязан подтвердить Redis, PostgreSQL, knowledge, хотя бы одну модель
и МИС. `live` проверяет только процесс.

После запуска проверить обе реплики отдельно:

```bash
.venv/bin/python scripts/inference_smoke.py \
  --chat-url http://127.0.0.1:8000 \
  --chat-url http://127.0.0.1:8002 \
  --embedding-url http://127.0.0.1:8001
```

Grafana доступна только через `127.0.0.1:3000`. Рабочие панели:
`VODC inference`, `VODC knowledge and RAG` и
`VODC safety and guardrails`. Prometheus rules находятся в
`ops/alert-rules.yml`; production-владелец обязан подключить их к принятому
каналу оповещения.

## База знаний

После изменения `knowledge_base/sources.json` или snapshots:

```bash
docker compose --profile gpu run --rm worker python -m app.worker --once
docker compose exec -T postgres psql -U vodc -d vodc -c \
  "SELECT url, enabled, reviewed_at, expires_at, indexed_at FROM knowledge_sources ORDER BY url"
docker compose exec -T postgres psql -U vodc -d vodc -c \
  "SELECT completed_at, stats FROM knowledge_index_runs ORDER BY completed_at DESC LIMIT 5"
```

Не включать источник при отсутствии владельца и даты проверки. Ошибка worker
до транзакции оставляет предыдущий индекс рабочим. После успешного цикла
`/health/ready` должен подтверждать knowledge dependency.

Production retrieval gate:

```bash
.venv/bin/python scripts/evaluate_retrieval.py \
  /secure/retrieval_gold.json --k 5 --minimum-recall 0.90 \
  --output artifacts/retrieval-report.json
```

## Деградация

- Одна vLLM-реплика недоступна: gateway продолжает round-robin; ошибочный
  запрос до первого токена повторяется на второй реплике. После начала
  потока ответ безопасно прерывается и не склеивается с другой моделью.
- МИС недоступна: не показывать цены/слоты, сохранить ссылки на публичные
  источники и штатную страницу записи.
- Embedding/RAG недоступны: не вызывать генерацию без источников.
- PostgreSQL/Redis недоступны: readiness 503; production-трафик не подавать.
- Output guardrail сработал: опасный фрагмент уже исключён из SSE. Сохранить
  только request/session ID из защищённого технического контура, остановить
  proactive invitation, воспроизвести кейс в red-team-наборе и не
  возобновлять пилот до классификации медицинским/safety-владельцем.

Проверка guardrails после обновления правил или модели:

```bash
.venv/bin/python scripts/run_policy_evals.py
curl --fail http://127.0.0.1:9090/api/v1/rules
```

## Backup

Запускать `scripts/backup_postgres.sh` ежедневно с защищёнными
`DATABASE_URL`, `BACKUP_DIRECTORY` и `BACKUP_ENCRYPTION_PASSWORD`.
Ротация по умолчанию 14 дней. Раз в месяц выполнять тестовое восстановление
в отдельную базу и проверять количество источников, chunks и событий.

## Rollback

1. Отключить proactive invitation.
2. Вернуть предыдущий digest приложения и vLLM в `.env`.
3. Выполнить `docker compose --profile gpu up -d`.
4. Выполнить `scripts/inference_smoke.py`, проверить live/ready и один
   разрешённый, refusal и booking сценарий.
5. Миграции `001_initial.sql` и `002_knowledge_pipeline.sql` аддитивные;
   откат БД не требуется.

Немедленный stop: ПДн в журнале, любой output guardrail block,
запрещённый медицинский ответ,
несанкционированное действие МИС или неподтверждённый критический факт.
