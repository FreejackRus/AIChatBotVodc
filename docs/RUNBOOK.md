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

Grafana доступна только через `127.0.0.1:3000`. Рабочая панель:
`VODC / VODC inference`. Prometheus rules находятся в
`ops/alert-rules.yml`; production-владелец обязан подключить их к принятому
каналу оповещения.

## Деградация

- Одна vLLM-реплика недоступна: gateway продолжает round-robin; ошибочный
  запрос до первого токена повторяется на второй реплике. После начала
  потока ответ безопасно прерывается и не склеивается с другой моделью.
- МИС недоступна: не показывать цены/слоты, сохранить ссылки на публичные
  источники и штатную страницу записи.
- Embedding/RAG недоступны: не вызывать генерацию без источников.
- PostgreSQL/Redis недоступны: readiness 503; production-трафик не подавать.

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
5. Миграция `001_initial.sql` аддитивная; откат БД не требуется.

Немедленный stop: ПДн в журнале, запрещённый медицинский ответ,
несанкционированное действие МИС или неподтверждённый критический факт.
