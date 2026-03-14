from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import skills as skills_router
from src.skills.registry import clear_skills_cache


def test_skills_endpoint_returns_research_skills():
    clear_skills_cache()
    app = FastAPI()
    app.include_router(skills_router.router, prefix="/api")
    client = TestClient(app)

    resp = client.get("/api/skills?domain=research")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    assert len(data) == 4
    assert [row["id"] for row in data] == [
        "/paper-summary",
        "/experiment-compare",
        "/innovation-summary",
        "/research-gaps",
    ]
    assert data[0]["label_cn"] == "论文总结"
    assert "description_cn" in data[0]
