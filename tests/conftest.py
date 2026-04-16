import sys
from pathlib import Path
import types


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    import chromadb  # noqa: F401
except Exception:
    class _DummyCollection:
        def __init__(self):
            self._rows = []

        def count(self):
            return len(self._rows)

        def add(self, ids=None, embeddings=None, documents=None, metadatas=None):
            ids = ids or []
            documents = documents or []
            metadatas = metadatas or []
            for idx, doc in enumerate(documents):
                self._rows.append(
                    {
                        "id": ids[idx] if idx < len(ids) else f"doc-{len(self._rows) + idx}",
                        "document": doc,
                        "metadata": metadatas[idx] if idx < len(metadatas) else {},
                    }
                )

        def query(self, query_embeddings=None, n_results=5, where=None):  # pragma: no cover - safety stub
            matched = []
            for row in self._rows[:n_results]:
                meta = row.get("metadata", {})
                if where and any(meta.get(key) != value for key, value in where.items()):
                    continue
                matched.append(row)
            return {
                "documents": [[row["document"] for row in matched]],
                "metadatas": [[row["metadata"] for row in matched]],
                "distances": [[0.0 for _ in matched]],
                "ids": [[row["id"] for row in matched]],
            }

        def get(self, where=None, include=None):
            matched = []
            for row in self._rows:
                meta = row.get("metadata", {})
                if where and any(meta.get(key) != value for key, value in where.items()):
                    continue
                matched.append(row)
            return {
                "ids": [row["id"] for row in matched],
                "documents": [row["document"] for row in matched],
                "metadatas": [row["metadata"] for row in matched],
            }

        def delete(self, ids=None):
            ids = set(ids or [])
            self._rows = [row for row in self._rows if row["id"] not in ids]

        def update(self, ids=None, metadatas=None):
            ids = ids or []
            metadatas = metadatas or []
            for idx, row_id in enumerate(ids):
                for row in self._rows:
                    if row["id"] == row_id:
                        row["metadata"] = metadatas[idx] if idx < len(metadatas) else row["metadata"]
                        break

    class _DummyClient:
        def __init__(self, *args, **kwargs):
            self._collection = _DummyCollection()

        def get_or_create_collection(self, *args, **kwargs):
            return self._collection

    class _DummySettings:
        def __init__(self, *args, **kwargs):
            pass

    chromadb_mod = types.ModuleType("chromadb")
    chromadb_mod.PersistentClient = _DummyClient
    chromadb_config_mod = types.ModuleType("chromadb.config")
    chromadb_config_mod.Settings = _DummySettings

    sys.modules["chromadb"] = chromadb_mod
    sys.modules["chromadb.config"] = chromadb_config_mod
