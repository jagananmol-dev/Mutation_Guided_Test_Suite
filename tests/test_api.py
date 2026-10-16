import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("langgraph")
from fastapi.testclient import TestClient
from api.main import app


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_generate_input_validation_rejects_empty_source():
    response = TestClient(app).post("/generate", json={"source_code": ""})
    assert response.status_code == 422
