from src.evaluation.service import EvaluationService


class _FakeOrchestrator:
    def execute_sync(self, mode: str, payload: dict):
        return {
            "output": "这是回答 [1]",
            "sources": [{"source": "doc-a", "page": 1, "content": "evidence text"}],
        }


def _dataset(n: int = 120) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append(
            {
                "id": f"id-{i}",
                "task_type": "single_hop",
                "mode": "research",
                "query": f"q-{i}",
                "kb_id": None,
                "expected_sources": ["doc-a"],
            }
        )
    return rows


def test_evaluation_gate_pass(monkeypatch, tmp_path):
    svc = EvaluationService(data_dir=tmp_path)
    monkeypatch.setattr("src.evaluation.service.get_orchestrator_service", lambda: _FakeOrchestrator())
    monkeypatch.setattr("src.evaluation.service.faithfulness", lambda answer, sources: 0.9)
    monkeypatch.setattr("src.evaluation.service.helpfulness", lambda answer, question: 0.9)

    report = svc._evaluate_dataset(_dataset())
    assert report["status"] == "pass"
    assert report["gate"]["Citation Precision >= 0.85"] is True
    assert report["gate"]["Faithfulness >= 0.80"] is True


def test_evaluation_gate_blocked_when_faithfulness_low(monkeypatch, tmp_path):
    svc = EvaluationService(data_dir=tmp_path)
    monkeypatch.setattr("src.evaluation.service.get_orchestrator_service", lambda: _FakeOrchestrator())
    monkeypatch.setattr("src.evaluation.service.faithfulness", lambda answer, sources: 0.2)
    monkeypatch.setattr("src.evaluation.service.helpfulness", lambda answer, question: 0.9)

    report = svc._evaluate_dataset(_dataset())
    assert report["status"] == "blocked"
    assert report["gate"]["Faithfulness >= 0.80"] is False
