import json
from pathlib import Path

from scripts.rebuild_vector_store import rebuild


def test_rebuild_vector_store_is_idempotent(tmp_path):
    source = (
        Path(__file__).resolve().parents[1] / "knowledge_base" / "vector_store.json"
    )
    store = tmp_path / "vector_store.json"
    store.write_bytes(source.read_bytes())

    first = rebuild(store)
    second = rebuild(store)
    data = json.loads(store.read_text(encoding="utf-8"))

    assert first["after"] == 24
    assert second == {"before": 24, "after": 24, "embedded": 24}
    assert data["metadata"]["total_chunks"] == 24
    assert (
        len(
            {
                (document["filename"], document["chunk_id"])
                for document in data["documents"]
            }
        )
        == 24
    )


def test_rebuild_prefers_latest_successful_embedding(tmp_path):
    store = tmp_path / "vector_store.json"
    store.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "content": "old",
                        "filename": "doc.md",
                        "chunk_id": 0,
                        "metadata": {"file_size": 10},
                        "embedding": [1.0, 0.0],
                    },
                    {
                        "content": "new",
                        "filename": "doc.md",
                        "chunk_id": 0,
                        "metadata": {"file_size": 20},
                        "embedding": [0.0, 1.0],
                    },
                    {
                        "content": "failed-newer",
                        "filename": "doc.md",
                        "chunk_id": 0,
                        "metadata": {"file_size": 30},
                        "embedding": None,
                    },
                ],
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )

    rebuild(store)
    document = json.loads(store.read_text(encoding="utf-8"))["documents"][0]

    assert document["content"] == "new"
    assert document["embedding"] == [0.0, 1.0]
