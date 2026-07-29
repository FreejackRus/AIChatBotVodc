#!/usr/bin/env python3
"""Атомарно удалить дубликаты из существующего JSON vector store.

Скрипт не генерирует новые embeddings. Для каждого (filename, chunk_id)
сохраняется запись с непустым embedding, а при равенстве — первая запись.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _document_key(document: dict[str, Any]) -> tuple[str, int]:
    return str(document["filename"]), int(document["chunk_id"])


def rebuild(
    store_path: Path,
    output_path: Path | None = None,
) -> dict[str, int]:
    with store_path.open("r", encoding="utf-8") as source:
        data = json.load(source)

    original_documents = data.get("documents", [])
    deduplicated: dict[tuple[str, int], dict[str, Any]] = {}

    for raw_document in original_documents:
        document = dict(raw_document)
        key = _document_key(document)
        metadata = dict(document.get("metadata") or {})
        metadata["content_hash"] = hashlib.sha256(
            str(document.get("content", "")).encode("utf-8")
        ).hexdigest()
        document["metadata"] = metadata

        existing = deduplicated.get(key)
        # Последняя успешно embedded-запись является самой свежей версией
        # чанка. Запись без embedding не должна затирать рабочую.
        if existing is None or document.get("embedding"):
            deduplicated[key] = document

    documents = [
        deduplicated[key]
        for key in sorted(deduplicated, key=lambda item: (item[0], item[1]))
    ]
    embedded_documents = [
        document for document in documents if document.get("embedding")
    ]
    dimensions = {len(document["embedding"]) for document in embedded_documents}
    if not embedded_documents:
        raise RuntimeError("Индекс не содержит ни одного embedding")
    if len(dimensions) != 1:
        raise RuntimeError(
            f"Индекс содержит embeddings разной размерности: {sorted(dimensions)}"
        )

    metadata = dict(data.get("metadata") or {})
    metadata.update(
        {
            "total_documents": len({document["filename"] for document in documents}),
            "total_chunks": len(documents),
            "embedded_chunks": len(embedded_documents),
            "embedding_dimension": dimensions.pop(),
            "index_format_version": 1,
        }
    )
    if len(original_documents) != len(documents) or "deduplicated_at" not in metadata:
        metadata["deduplicated_at"] = datetime.now(timezone.utc).isoformat()
    output = {"documents": documents, "metadata": metadata}

    destination = output_path or store_path
    if destination == store_path and output == data:
        return {
            "before": len(original_documents),
            "after": len(documents),
            "embedded": len(embedded_documents),
        }

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix="vector_store.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(output, temp_file, ensure_ascii=False)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, destination)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()

    return {
        "before": len(original_documents),
        "after": len(documents),
        "embedded": len(embedded_documents),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "store",
        nargs="?",
        type=Path,
        default=Path("knowledge_base/vector_store.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Записать очищенный индекс в другой файл",
    )
    args = parser.parse_args()
    result = rebuild(
        args.store.resolve(),
        args.output.resolve() if args.output else None,
    )
    print(
        "Индекс очищен: "
        f"{result['before']} → {result['after']} чанков, "
        f"embeddings: {result['embedded']}"
    )


if __name__ == "__main__":
    main()
