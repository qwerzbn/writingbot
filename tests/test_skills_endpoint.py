from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers import skills as skills_router
from src.skills.registry import clear_skills_cache


def test_skills_endpoint_returns_empty_after_research_module_removal():
    clear_skills_cache()
    app = FastAPI()
    app.include_router(skills_router.router, prefix="/api")
    client = TestClient(app)

    resp = client.get("/api/skills?domain=research")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert isinstance(data, list)
    assert data == []
