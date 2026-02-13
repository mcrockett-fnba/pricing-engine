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
    assert data["models"]["status"] in ("loaded", "not_loaded")


def test_model_status_returns_200():
    response = client.get("/api/models/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("loaded", "not_loaded")
    if data["status"] == "loaded":
        assert "models" in data
        for name in ("survival", "deq", "default", "recovery", "prepayment"):
            assert name in data["models"]


def test_valuation_no_body_returns_422():
    response = client.post("/api/valuations/run")
    assert response.status_code == 422
