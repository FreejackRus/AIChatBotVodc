# CI и migration gates

GitHub Actions workflow `.github/workflows/ci.yml` запускается для каждого
pull request и каждого push в `master`.

## Quality job

CPU-only job без внешних секретов выполняет:

1. установку закреплённых runtime/dev dependencies;
2. `ruff check .`;
3. полный `pytest`;
4. проверку архитектурных границ;
5. safety/privacy/output policy evals;
6. `docker compose config --quiet`.

Job намеренно не скачивает модели с Hugging Face и не запускает vLLM.
Model revisions проверяются репозиторными контрактами, а фактические GPU,
TTFT и load gates выполняются на целевом сервере.

## Migration job

Отдельный job поднимает чистый `pgvector/pgvector:pg16` и запускает
`scripts/check_migrations.sh`.

Скрипт:

- применяет все `migrations/*.sql` в лексикографическом порядке;
- повторяет полный цикл для проверки идемпотентности;
- проверяет наличие таблиц ingestion, audit, staging и publisher;
- проверяет тип `knowledge_chunks.embedding = vector(1024)`;
- проверяет безопасный default `knowledge_sources.origin = manual`.

Локальный запуск при доступном PostgreSQL:

```bash
DATABASE_URL='postgresql://vodc:vodc@127.0.0.1:5432/vodc' \
  scripts/check_migrations.sh
```

## Внешние production gates

Зелёный CI не заменяет:

- benchmark и нагрузку на 2×RTX 5090;
- утверждённый retrieval gold set;
- contract tests фактического API «МедАнгел»;
- медицинское и privacy-согласование;
- backup/restore и TLS-проверку production.

PR нельзя сливать при красном quality или migration job. Production-пилот
нельзя запускать только на основании зелёного репозиторного CI.

Mock contract tests `tests/test_medangel_adapter.py` входят в полный
`pytest` и проверяют fail-closed границу, кеш, retry и live validation. Они
не заменяют fixtures реального тестового стенда.
