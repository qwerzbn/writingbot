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
