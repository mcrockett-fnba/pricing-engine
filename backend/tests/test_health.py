from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert "models" in data


def test_model_status_returns_200():
    response = client.get("/api/models/status")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert data["models"]["survival"]["status"] == "stub"


def test_valuation_returns_501():
    response = client.post("/api/valuations/run")
    assert response.status_code == 501
