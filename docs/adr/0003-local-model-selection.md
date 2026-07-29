# ADR-0003: Qwen3.5-9B как основная локальная модель

- Статус: принято условно, до GPU benchmark
- Дата: 2026-07-29

## Контекст

Целевая машина содержит 2×RTX 5090 по 32 GiB. Нужны две независимые реплики,
русский язык, instruction following, контекст 8192 и до десяти активных
последовательностей на реплику. Vision, voice и fine-tuning не входят в MVP.

Рассмотрены:

- `Qwen/Qwen3.5-9B`, BF16;
- `Qwen/Qwen3.5-35B-A3B-GPTQ-Int4`, MoE challenger.

`hf-mem` при 8192 токенах, batch 10 и FP8 KV оценивает соответственно
24 674 925 536 и 27 758 605 408 байт. Оценка не включает CUDA graphs и
allocator overhead.

## Решение

Основная модель — `Qwen/Qwen3.5-9B` с зафиксированным revision. Каждая GPU
обслуживает независимую реплику. Используются `--language-model-only`,
`--kv-cache-dtype fp8_e4m3`, `--max-model-len 8192`,
`--max-num-seqs 10`; thinking отключён на уровне chat template.

35B GPTQ остаётся challenger. Он может заменить основную модель только после
улучшения на VODC control/gold set и прохождения тех же latency, concurrency,
memory и failover gates.

## Последствия

- основная модель имеет больший эксплуатационный запас памяти;
- embedding может остаться на GPU 0;
- общие benchmark model card не заменяют доменную оценку;
- окончательное принятие требует реального запуска на 2×RTX 5090.
