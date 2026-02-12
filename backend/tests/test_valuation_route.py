"""Tests for the POST /api/valuations/run endpoint."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

_SAMPLE_LOAN = {
    "loan_id": "L001",
    "unpaid_balance": 200_000.0,
    "interest_rate": 0.065,
    "original_term": 360,
    "remaining_term": 120,
    "loan_age": 240,
    "credit_score": 720,
    "ltv": 0.75,
}

_SAMPLE_PACKAGE = {
    "package_id": "PKG-001",
    "name": "Test Package",
    "loan_count": 1,
    "total_upb": 200_000.0,
    "purchase_price": 190_000.0,
    "loans": [_SAMPLE_LOAN],
}


def test_valuation_returns_200():
    response = client.post("/api/valuations/run", json={
        "package": _SAMPLE_PACKAGE,
    })
    assert response.status_code == 200


def test_valuation_response_structure():
    response = client.post("/api/valuations/run", json={
        "package": _SAMPLE_PACKAGE,
        "config": {"n_simulations": 5, "include_stochastic": True, "stochastic_seed": 42},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["package_id"] == "PKG-001"
    assert data["loan_count"] == 1
    assert "expected_npv" in data
    assert "roe" in data
    assert "roe_annualized" in data
    assert "npv_by_scenario" in data
    assert "loan_results" in data
    assert len(data["loan_results"]) == 1
    assert data["loan_results"][0]["loan_id"] == "L001"


def test_valuation_single_loan_has_cash_flows():
    response = client.post("/api/valuations/run", json={
        "package": _SAMPLE_PACKAGE,
        "config": {"n_simulations": 0, "include_stochastic": False},
    })
    data = response.json()
    loan_result = data["loan_results"][0]
    assert len(loan_result["monthly_cash_flows"]) > 0
    assert loan_result["monthly_cash_flows"][0]["month"] == 1


def test_valuation_custom_config_small_n():
    response = client.post("/api/valuations/run", json={
        "package": _SAMPLE_PACKAGE,
        "config": {"n_simulations": 10, "include_stochastic": True, "stochastic_seed": 42},
    })
    data = response.json()
    # 3 scenarios × 10 sims = 30 MC runs
    loan_result = data["loan_results"][0]
    assert len(loan_result["pv_distribution"]) == 30


def test_valuation_no_body_returns_422():
    response = client.post("/api/valuations/run")
    assert response.status_code == 422
