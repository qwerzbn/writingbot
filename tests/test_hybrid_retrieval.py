import builtins

from src.retrieval.hybrid import EvidenceJudge, HybridRetrievalService
from src.retrieval.index_store import KnowledgeIndexStore


def test_evidence_judge_filters_low_quality():
    judge = EvidenceJudge()
    rows = [
        {
            "doc_id": "bad",
            "content": "too short",
            "metadata": {},
            "fusion_score": 0.1,
        },
        {
            "doc_id": "good",
            "content": "A" * 160,
            "metadata": {"source": "paper.pdf", "page": 3},
            "fusion_score": 0.9,
        },
    ]
    judged = judge.judge(rows)
    by_id = {x["doc_id"]: x for x in judged}
    assert by_id["bad"]["judge_keep"] is False
    assert by_id["bad"]["factual_risk"] > 0.7
    assert by_id["good"]["judge_keep"] is True
    assert by_id["good"]["relevance"] >= 0.35


def test_rrf_fusion_and_context_budget(tmp_path):
    service = HybridRetrievalService(index_store=KnowledgeIndexStore(tmp_path))

    vector_rows = [
        {"doc_id": "d1", "content": "A" * 220, "metadata": {"source": "s1", "page": 1}},
        {"doc_id": "d2", "content": "B" * 220, "metadata": {"source": "s2", "page": 2}},
    ]
    bm25_rows = [
        {"doc_id": "d2", "content": "B" * 220, "metadata": {"source": "s2", "page": 2}},
        {"doc_id": "d3", "content": "C" * 220, "metadata": {"source": "s3", "page": 3}},
    ]
    graph_rows = [
        {"doc_id": "d3", "content": "C" * 220, "metadata": {"source": "s3", "page": 3}},
        {"doc_id": "d1", "content": "A" * 220, "metadata": {"source": "s1", "page": 1}},
    ]

    fused = service._fuse_rrf(vector_rows, bm25_rows, graph_rows, weights=(0.5, 0.3, 0.2), top_k=5)
    assert fused
    assert all(0.0 <= row["fusion_score"] <= 1.0 for row in fused)

    context, sources = service.build_context(fused, token_budget=100)
    # 220 chars ~= 62 tokens, should keep only one chunk at budget 100.
    assert len(sources) == 1
    assert context.startswith("[1]")


def test_retrieve_reports_stage_timings(tmp_path):
    service = HybridRetrievalService(index_store=KnowledgeIndexStore(tmp_path))

    class FakeVectorStore:
        def search(self, query: str, top_k: int):
            return [
                {
                    "content": "retrieval timing evidence " * 12,
                    "metadata": {"source": "timing.pdf", "page": 1},
                    "score": 0.9,
                }
            ][:top_k]

    result = service.retrieve(
        kb_id="kb-timing",
        vector_store=FakeVectorStore(),
        query="retrieval timing",
        top_k=1,
    )

    timings = result["timings_ms"]
    assert set(timings) >= {"vector_ms", "bm25_ms", "graph_ms", "fusion_ms", "rerank_ms", "judge_ms"}
    assert all(isinstance(value, int) and value >= 0 for value in timings.values())


def test_index_store_caches_local_index_reads_for_repeated_retrieval(tmp_path, monkeypatch):
    store = KnowledgeIndexStore(tmp_path)
    store.rebuild_from_chunks(
        "kb-cache",
        [
            {
                "content": "retrieval cache latency evidence " * 12,
                "metadata": {"source": "cache.pdf", "page": 1},
            }
        ],
    )
    service = HybridRetrievalService(index_store=store)

    class FakeVectorStore:
        def search(self, query: str, top_k: int):
            return [
                {
                    "content": "retrieval cache latency evidence " * 12,
                    "metadata": {"source": "cache.pdf", "page": 1},
                    "score": 0.9,
                }
            ]

    counts = {"docs": 0, "stats": 0, "graph": 0}
    real_open = builtins.open

    def counting_open(path, *args, **kwargs):
        raw = str(path)
        if raw.endswith("docs.jsonl"):
            counts["docs"] += 1
        elif raw.endswith("bm25_stats.json"):
            counts["stats"] += 1
        elif raw.endswith("concept_graph.json"):
            counts["graph"] += 1
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", counting_open)

    service.retrieve(kb_id="kb-cache", vector_store=FakeVectorStore(), query="cache latency", top_k=1)
    service.retrieve(kb_id="kb-cache", vector_store=FakeVectorStore(), query="cache latency", top_k=1)

    assert counts == {"docs": 1, "stats": 1, "graph": 1}


def test_evidence_judge_boosts_query_matching_evidence():
    judge = EvidenceJudge()
    judged = judge.judge(
        [
            {
                "doc_id": "vector-only",
                "content": "General introduction " * 20,
                "metadata": {"source": "paper.pdf", "page": 1},
                "rerank_score": 1.0,
            },
            {
                "doc_id": "query-match",
                "content": "Retrieval cache latency and hybrid search accuracy " * 8,
                "metadata": {"source": "paper.pdf", "page": 2, "section": "retrieval latency"},
                "rerank_score": 0.7,
            },
        ],
        query="retrieval latency accuracy",
    )

    assert judged[0]["doc_id"] == "query-match"
    assert judged[0]["query_overlap"] > judged[1]["query_overlap"]
