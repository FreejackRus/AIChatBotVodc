#!/usr/bin/env python3
"""Fail-fast checks for a two-GPU vLLM Docker host."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass


class PreflightError(RuntimeError):
    """The host cannot safely start the configured inference stack."""


@dataclass(frozen=True)
class GPU:
    index: int
    name: str
    memory_mib: int
    driver: str


def parse_gpu_inventory(output: str) -> list[GPU]:
    inventory: list[GPU] = []
    for line_number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 4:
            raise PreflightError(
                f"Неожиданный формат nvidia-smi в строке {line_number}"
            )
        try:
            inventory.append(
                GPU(
                    index=int(parts[0]),
                    name=parts[1],
                    memory_mib=int(parts[2]),
                    driver=parts[3],
                )
            )
        except ValueError as exc:
            raise PreflightError(
                f"Некорректные числовые данные nvidia-smi в строке {line_number}"
            ) from exc
    return inventory


def _run(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise PreflightError(f"Команда {command[0]} не установлена") from exc
    except subprocess.TimeoutExpired as exc:
        raise PreflightError(f"Команда {command[0]} превысила таймаут") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        suffix = f": {detail}" if detail else ""
        raise PreflightError(f"Команда {' '.join(command)} завершилась ошибкой{suffix}")
    return result.stdout.strip()


def inspect_host(min_gpus: int, min_memory_mib: int) -> list[GPU]:
    for executable in ("docker", "nvidia-smi"):
        if shutil.which(executable) is None:
            raise PreflightError(f"{executable} не найден в PATH")

    _run(["docker", "compose", "version"])
    runtimes_raw = _run(["docker", "info", "--format", "{{json .Runtimes}}"])
    try:
        runtimes = json.loads(runtimes_raw)
    except json.JSONDecodeError as exc:
        raise PreflightError("Docker вернул некорректный список runtime") from exc
    if "nvidia" not in runtimes:
        raise PreflightError(
            "NVIDIA Container Toolkit не зарегистрирован как Docker runtime"
        )

    inventory = parse_gpu_inventory(
        _run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ]
        )
    )
    if len(inventory) < min_gpus:
        raise PreflightError(
            f"Найдено GPU: {len(inventory)}, требуется не меньше {min_gpus}"
        )
    undersized = [gpu for gpu in inventory[:min_gpus] if gpu.memory_mib < min_memory_mib]
    if undersized:
        values = ", ".join(
            f"GPU {gpu.index}: {gpu.memory_mib} MiB" for gpu in undersized
        )
        raise PreflightError(
            f"Недостаточно VRAM (минимум {min_memory_mib} MiB): {values}"
        )
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Проверка Docker/NVIDIA host перед запуском vLLM."
    )
    parser.add_argument("--min-gpus", type=int, default=2)
    parser.add_argument("--min-memory-mib", type=int, default=30_000)
    args = parser.parse_args()
    if args.min_gpus < 1 or args.min_memory_mib < 1:
        parser.error("минимальные значения должны быть положительными")

    try:
        inventory = inspect_host(args.min_gpus, args.min_memory_mib)
    except PreflightError as exc:
        print(f"Preflight failed: {exc}", file=sys.stderr)
        return 1

    print("Inference host preflight passed:")
    for gpu in inventory:
        print(
            f"- GPU {gpu.index}: {gpu.name}, "
            f"{gpu.memory_mib} MiB, driver {gpu.driver}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
