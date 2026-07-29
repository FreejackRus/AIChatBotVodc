# Развёртывание

Актуальная конфигурация использует Docker Compose, FastAPI, PostgreSQL,
Redis и vLLM.

## Подготовка

```bash
cp .env.production .env
chmod 600 .env
```

Замените все `REPLACE_*`, укажите реальный API «МедАнгел», TLS-сертификаты
`ssl/cert.pem` и `ssl/key.pem`, а также одобренный digest `VLLM_IMAGE`.

## Проверка и запуск

```bash
docker compose --profile gpu config
.venv/bin/python scripts/inference_preflight.py
./deploy.sh
curl --fail https://chat.vodc.ru/health/live
curl --fail https://chat.vodc.ru/health/ready
```

`deploy.sh` ждёт healthy-состояния двух chat-реплик и embedding, проверяет
SSE/TTFT, запускает однократную индексацию и только затем проверяет readiness
приложения. Таймаут первичной загрузки моделей задаётся
`DEPLOY_WAIT_TIMEOUT_SECONDS` (по умолчанию 1800).

До подачи публичного трафика выполните:

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/run_policy_evals.py
.venv/bin/python scripts/validate_retrieval_gold.py /secure/retrieval_gold.json
.venv/bin/python scripts/load_test.py --base-url https://chat.vodc.ru
```

Prometheus и Grafana слушают только loopback (`9090` и `3000`). Доступ
администратора выполняется через SSH tunnel. Полный inference runbook и GPU
gate: [docs/STAGE_3_INFERENCE.md](docs/STAGE_3_INFERENCE.md).

Эксплуатация, backup и rollback: [docs/RUNBOOK.md](docs/RUNBOOK.md).
