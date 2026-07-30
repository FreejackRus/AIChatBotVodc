#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${project_dir}"

if [[ ! -f .env ]]; then
    echo "Missing protected .env; use .env.production as a template." >&2
    exit 1
fi

set -a
source .env
set +a

: "${SIGNING_SECRET:?SIGNING_SECRET is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD is required}"

compose=(docker compose)
if [[ "${ENABLE_GPU_PROFILE:-true}" == "true" ]]; then
    compose+=(--profile gpu)
fi
wait_timeout="${DEPLOY_WAIT_TIMEOUT_SECONDS:-1800}"

"${compose[@]}" config --quiet

if [[ -x .venv/bin/python ]]; then
    .venv/bin/python -m pytest
    .venv/bin/python scripts/check_architecture.py
    .venv/bin/python scripts/run_policy_evals.py
fi

"${compose[@]}" build api worker
"${compose[@]}" up -d postgres redis

for _ in $(seq 1 30); do
    if "${compose[@]}" exec -T postgres pg_isready -U vodc -d vodc >/dev/null; then
        break
    fi
    sleep 2
done

for migration in migrations/*.sql; do
    "${compose[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U vodc -d vodc \
        < "${migration}"
done

if [[ "${ENABLE_GPU_PROFILE:-true}" == "true" ]]; then
    if [[ -x .venv/bin/python ]]; then
        .venv/bin/python scripts/inference_preflight.py
    else
        python3 scripts/inference_preflight.py
    fi
    "${compose[@]}" up -d --wait --wait-timeout "${wait_timeout}" \
        vllm-primary vllm-secondary vllm-embedding dcgm-exporter
fi

"${compose[@]}" up -d --wait --wait-timeout "${wait_timeout}" \
    api prometheus grafana
"${compose[@]}" run --rm worker python -m app.worker --once
"${compose[@]}" up -d --wait --wait-timeout "${wait_timeout}" worker

if [[ "${ENABLE_GPU_PROFILE:-true}" == "true" ]]; then
    "${compose[@]}" exec -T api python scripts/inference_smoke.py \
        --chat-url http://vllm-primary:8000 \
        --chat-url http://vllm-secondary:8000 \
        --chat-model "${CHAT_MODEL:-Qwen3.5-9B}" \
        --embedding-url http://vllm-embedding:8000 \
        --embedding-model "${EMBEDDING_MODEL:-Qwen3-Embedding-0.6B}" \
        --ttft-limit "${MODEL_TTFT_LIMIT_SECONDS:-10}"
fi

"${compose[@]}" exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health/ready', timeout=10)"
"${compose[@]}" up -d --wait --wait-timeout "${wait_timeout}" nginx
"${compose[@]}" ps

echo "Deployment completed: inference smoke and /health/ready passed."
