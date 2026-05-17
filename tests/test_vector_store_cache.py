from __future__ import annotations

from src.knowledge.vector_store import VectorStore


def test_vector_store_caches_query_embeddings_for_repeated_search():
    embed_calls: list[list[str]] = []

    class FakeCollection:
        def query(self, **kwargs):
            return {
                "documents": [["cached evidence"]],
                "metadatas": [[{"source": "paper.pdf", "page": 1}]],
                "distances": [[0.1]],
            }

    store = VectorStore.__new__(VectorStore)
    store._collection = FakeCollection()

    def fake_embed(texts):
        embed_calls.append(list(texts))
        return [[0.1, 0.2, 0.3] for _ in texts]

    store._embed = fake_embed

    first = store.search("same query", top_k=1)
    second = store.search("same query", top_k=1)

    assert first == second
    assert embed_calls == [["same query"]]
