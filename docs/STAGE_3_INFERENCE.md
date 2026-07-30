# Этап 3. Локальный inference и среда

Статус: код, Compose-контур, проверки и мониторинг реализованы. Финальная
GPU-приёмка выполняется на целевом сервере 2×RTX 5090, потому что в среде
разработки нет доступного NVIDIA driver и Docker daemon.

## Результат

| Требование | Реализация |
|---|---|
| Две независимые chat-реплики | `vllm-primary` на GPU 0 и `vllm-secondary` на GPU 1 |
| Локальный embedding | `vllm-embedding` на GPU 0 |
| Потоковый inference API | OpenAI-compatible `/v1/chat/completions`, SSE |
| Health-check | `/health` у каждой vLLM-службы, startup period 10 минут |
| Failover | model gateway повторяет запрос на другой реплике только до первого токена |
| Проверка host | `scripts/inference_preflight.py` |
| Runtime smoke | `scripts/inference_smoke.py` для обеих chat-реплик и embedding |
| Метрики | API, model gateway, vLLM `/metrics`, NVIDIA DCGM Exporter |
| Визуализация | provisioned Grafana dashboard `VODC / VODC inference` |
| Аварийные условия | Prometheus rules для API, реплик, TTFT, GPU temperature/XID |

Model API, Prometheus и Grafana привязаны только к `127.0.0.1`. Публично
доступен только Nginx. vLLM не включает request logging, Swagger/ReDoc и
access log, поэтому пользовательский текст не попадает в штатные журналы
inference.

## Раскладка GPU

| GPU | Служба | Memory utilization |
|---|---|---:|
| 0 | Qwen3.5-9B primary | 0,82 |
| 0 | Qwen3-Embedding-0.6B | 0,12 |
| 1 | Qwen3.5-9B secondary | 0,90 |

Суммарный лимит GPU 0 равен 0,94; оставшийся запас предназначен для CUDA
context, DCGM и пиковых аллокаций. Контекст chat ограничен 8192 токенами,
одновременно допускается 10 sequences на реплику. KV cache использует
`fp8_e4m3`.

Точные значения должны быть пересмотрены при смене checkpoint, версии vLLM
или driver. OOM означает провал приёмки, а не основание автоматически
сокращать контекст.

## Подготовка host

Обязательно:

- два NVIDIA GPU с не менее чем 30 000 MiB VRAM каждый;
- рабочие `nvidia-smi`, Docker Engine, Docker Compose с `up --wait`;
- NVIDIA Container Toolkit, зарегистрированный runtime `nvidia`;
- доступ к Hugging Face Hub и NVIDIA NGC для первичной загрузки;
- не менее 100 GiB свободного диска под кеш и образы.

Проверка не меняет состояние host:

```bash
.venv/bin/python scripts/inference_preflight.py
```

Модели и revisions закреплены в `.env.production`. Long tag DCGM Exporter
неизменяемый по правилам проекта NVIDIA. Для production после проверки
следует дополнительно зафиксировать image digest vLLM в защищённом `.env`.

## Запуск и приёмка

```bash
cp .env.production .env
chmod 600 .env
./deploy.sh
```

`deploy.sh`:

1. валидирует Compose и запускает локальные тесты;
2. собирает API/worker и применяет миграции;
3. выполняет GPU preflight;
4. ждёт healthy для двух chat-реплик и embedding;
5. проверяет модельные ID, SSE, содержательный первый токен, TTFT ≤ 10 с и
   размер embedding;
6. запускает индексацию и требует успешный `/health/ready`.

Повторный ручной smoke:

```bash
.venv/bin/python scripts/inference_smoke.py \
  --chat-url http://127.0.0.1:8000 \
  --chat-url http://127.0.0.1:8002 \
  --embedding-url http://127.0.0.1:8001
```

## Мониторинг

Локальные адреса host:

- Prometheus: `http://127.0.0.1:9090`;
- Grafana: `http://127.0.0.1:3000`;
- primary/secondary/embedding: порты `8000`, `8002`, `8001`.

Для удалённой эксплуатации используется SSH tunnel, а не публичный firewall
rule:

```bash
ssh -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 user@chat-host
```

Ключевые сигналы:

- `vodc_model_time_to_first_token_seconds`;
- `vodc_model_failovers_total`;
- `vllm:num_requests_running`, `vllm:num_requests_waiting`;
- `vllm:kv_cache_usage_perc`;
- `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_FB_USED`,
  `DCGM_FI_DEV_GPU_TEMP`, `DCGM_FI_DEV_XID_ERRORS`.

Prometheus оценивает alerts, но транспорт уведомлений и контакты дежурных
задаются на production-инфраструктуре и не хранятся в репозитории.

## Gate этапа

Репозиторный gate:

- Compose проходит `config --quiet`;
- все три inference endpoint имеют health-check;
- model API и панели мониторинга не слушают внешний интерфейс;
- smoke/preflight покрыты unit-тестами;
- Prometheus знает API, три vLLM endpoint и DCGM;
- dashboard и alert rules валидируются тестами.

GPU gate:

- обе RTX 5090 определены и имеют достаточный объём памяти;
- обе chat-реплики и embedding healthy;
- каждая chat-реплика выдаёт текст с TTFT не более 10 секунд;
- embedding возвращает непустой числовой вектор;
- API ready после индексации и подключения тестовой МИС;
- Grafana получает vLLM и DCGM series, XID равен нулю.

До сохранения отчёта GPU smoke этап нельзя считать production-принятым.
