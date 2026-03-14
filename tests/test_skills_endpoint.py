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
    skill_ids = {row["id"] for row in data}
    assert "/paper-find" in skill_ids
    assert "/citation-check" in skill_ids
