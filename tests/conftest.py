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
            self._docs = []

        def count(self):
            return len(self._docs)

        def add(self, ids=None, embeddings=None, documents=None, metadatas=None):
            documents = documents or []
            for doc in documents:
                self._docs.append(doc)

        def query(self, query_embeddings=None, n_results=5, where=None):  # pragma: no cover - safety stub
            return {
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
                "ids": [[]],
            }

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
